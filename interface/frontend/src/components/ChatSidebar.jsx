import { useEffect, useRef, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import { editImage, getApartment, streamChatMessage } from '../api';
import CauTraLoi from './CauTraLoi';
import { CloseIcon, SendIcon } from './Icons';

const QUICK_ASKS = ['Căn 2PN dưới 4 tỷ', 'Căn còn ở tòa S1', 'Tư vấn view đẹp'];

/**
 * Gợi ý cho chế độ sửa ảnh — mỗi câu là một THAO TÁC khác nhau mà lõi hỗ trợ:
 * xoá vật thể, thay bằng vật khác, đổi thuộc tính.
 *
 * Không phải trang trí. Ô nhập chỉ ghi "Bạn muốn sửa chi tiết nào trong ảnh?",
 * và không ai đoán ra là gõ được "đổi sofa thành ghế da" — chính người đặt hàng
 * tính năng này cũng tưởng nó chỉ biết xoá đồ vật.
 */
const GOI_Y_SUA_ANH = [
  'Thêm một chậu cây góc phòng',
  'Bỏ đồ đạc lặt vặt đi',
  'Đổi sofa thành ghế da',
  'Rèm màu sáng hơn',
];

// Backend chặn history ở 20 lượt (40 tin nhắn) và trả 422 nếu vượt. Lịch sử
// giữ nguyên trong sidebar suốt phiên nên sẽ chạm trần đó — cắt bớt trước khi
// gửi, giữ 30 tin gần nhất để còn biên an toàn.
const MAX_HISTORY = 30;

/**
 * Tiêu đề cho lời mời, ghép từ dữ liệu THẬT của căn.
 *
 * Chưa tải xong hoặc gọi hỏng thì hiện mã căn trơn — không bịa tên, không để
 * ô trống nhấp nháy.
 */
function tieuDeCan(maCan, can) {
  if (!can) return `Căn ${maCan}`;
  const phan = [can.loai_can, can.dien_tich, can.toa && `Tòa ${can.toa}`, can.gia].filter(Boolean);
  return phan.length ? `Căn ${maCan} — ${phan.join(' · ')}` : `Căn ${maCan}`;
}

const CO_MA_CAN = /\b[A-Za-z]{2,4}\d{2,5}\b/;

/**
 * Gắn mã căn đang mở vào câu hỏi khi người dùng nói trống không.
 *
 * "Phân tích cho tôi căn hiện tại" không có mã căn nào, nên tool tra tồn kho
 * không rút được tham số và im lặng — trợ lý đành trả lời "chưa đủ dữ liệu"
 * dù mã căn đang hiện ngay trên màn hình.
 *
 * Chỉ gắn khi câu hỏi CHƯA có mã căn: người dùng hỏi về căn khác trong lúc
 * đang mở một căn là chuyện bình thường, không được ghi đè ý họ.
 *
 * Bong bóng chat vẫn hiện nguyên văn người dùng gõ — phần gắn thêm chỉ đi theo
 * request, không sửa lời của họ trên màn hình.
 */
function themNguCanh(message, maCan) {
  if (!maCan || CO_MA_CAN.test(message)) return message;
  return `${message} (căn đang xem: ${maCan})`;
}

/** Câu hỏi gợi ý khi người dùng đang mở một căn cụ thể. */
const goiYTheoCan = (maCan) => [
  `Phân tích chi tiết căn ${maCan}`,
  `Căn ${maCan} còn không, giá bao nhiêu?`,
  `Có căn nào tương tự ${maCan} không?`,
];

const TEN_TOOL = {
  inventory_lookup: 'thông tin căn',
  inventory_search: 'danh sách căn',
};

/** Đổi event tiến trình của lõi AI thành một câu người đọc hiểu được. */
function moTaBuoc(event) {
  const { step, tools, found, chunks, action, tool, iteration } = event.data ?? {};

  if (step === 'router') return 'Đang xác định câu hỏi…';
  if (step === 'tools') {
    const ten = TEN_TOOL[(tools ?? [])[0]] ?? 'dữ liệu';
    return found ? `Đã tra ${ten} trong kho dữ liệu` : `Đã tra ${ten}, chưa thấy khớp`;
  }
  if (step === 'retrieve') return `Đang đọc ${chunks} đoạn tài liệu…`;

  // Vòng lặp agent: hiện thẳng lý do model tự nêu, đó chính là "suy luận" mà
  // người dùng muốn thấy. Chỉ ẩn nhánh clarify vì câu hỏi ngược sẽ hiện ngay
  // sau đó dưới dạng câu trả lời, nói trước là lặp.
  if (step === 'plan') return action === 'clarify' ? null : event.content || 'Đang cân nhắc bước tiếp theo…';
  if (step === 'act') {
    const ten = TEN_TOOL[tool] ?? tool;
    return `Đang tra ${ten}${iteration > 1 ? ` (lượt ${iteration})` : ''}…`;
  }
  return null;
}

/**
 * Trợ lý S — sidebar bên phải, thu gọn thành nút tròn chữ "S".
 *
 * Mở được cho cả khách chưa đăng nhập. Backend giới hạn số lượt theo IP nên khi
 * hỏi quá nhanh sẽ nhận lỗi 429 kèm số giây phải đợi — hiện nguyên văn câu đó
 * cho người dùng, không nuốt đi.
 *
 * Giữ lịch sử hội thoại trong state và gửi kèm mỗi lượt, đúng contract
 * POST /api/chat {message, history} -> {reply}.
 */
export default function ChatSidebar({ open, onToggle }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  // Dòng trạng thái "trợ lý đang làm gì", thay cho màn hình đứng im.
  const [buoc, setBuoc] = useState('');
  // Chữ đầu tiên đã về chưa — mốc để tắt chấm nhấp nháy.
  const [dangTraLoi, setDangTraLoi] = useState(false);
  // Đang đính kèm ảnh căn để nhờ sửa (bật bằng nút +).
  const [dinhKemAnh, setDinhKemAnh] = useState(false);
  // Ảnh đang xem phóng to; null là không mở.
  const [anhPhongTo, setAnhPhongTo] = useState(null);
  // Lõi AI cấp ở lượt đầu, gửi lại các lượt sau để log gom về một phiên.
  const sessionRef = useRef(null);
  // Đã mời phân tích căn nào rồi — không mời lại căn đó trong cùng phiên.
  const daMoiRef = useRef(new Set());
  const [boQua, setBoQua] = useState(false);
  const bodyRef = useRef(null);
  const inputRef = useRef(null);

  // Đang xem căn nào thì đọc thẳng từ URL, không cần tầng state dùng chung.
  const [thamSoUrl] = useSearchParams();
  const khop = useLocation().pathname.match(/^\/apartments\/([^/]+)/);
  const maCanDangXem = khop ? decodeURIComponent(khop[1]) : null;
  const [canDangXem, setCanDangXem] = useState(null);

  // Đổi sang căn khác thì cho phép mời lại, và nạp vài thông tin để lời mời nói
  // đúng căn nào thay vì chỉ trơ một mã căn.
  useEffect(() => {
    setBoQua(false);
    setCanDangXem(null);
    if (!maCanDangXem) return;

    let con_hieu_luc = true;
    getApartment(maCanDangXem)
      .then((data) => {
        if (con_hieu_luc) setCanDangXem(data);
      })
      .catch(() => {
        // Không lấy được thì vẫn mời, chỉ là hiện mã căn trơn.
      });
    return () => {
      con_hieu_luc = false;
    };
  }, [maCanDangXem]);

  const moiPhanTich = Boolean(
    maCanDangXem && !boQua && !daMoiRef.current.has(maCanDangXem),
  );

  // Đúng tấm đang hiện lớn bên trái. Trang chi tiết ghi chỉ số vào `?anh=`, nên
  // người dùng bấm sang ảnh khác là ngữ cảnh sửa ảnh đổi theo — trước đây luôn
  // lấy ảnh đầu tiên, bấm sang tấm thứ ba rồi nhờ sửa thì vẫn sửa tấm thứ nhất.
  const chiSoAnh = Math.max(0, Number(thamSoUrl.get('anh')) || 0);
  const danhSachAnh = canDangXem?.images ?? [];
  const anhGoc = danhSachAnh[Math.min(chiSoAnh, danhSachAnh.length - 1)]?.image_url ?? null;

  // Ảnh vừa chỉnh xong, dùng làm nguồn cho lượt sau. Đây là mặc định: người dùng
  // sửa dần từng bước ("bỏ cái quạt" rồi "rèm sáng hơn") thì mỗi bước phải cộng
  // dồn lên bước trước, không phải quay về ảnh gốc.
  const [anhDaSua, setAnhDaSua] = useState(null);
  const anhChinh = anhDaSua ?? anhGoc;

  // Đổi căn hoặc đổi tấm ảnh thì chuỗi sửa cũ hết hiệu lực.
  useEffect(() => setAnhDaSua(null), [maCanDangXem, chiSoAnh]);

  /**
   * Gửi một lượt sửa ảnh.
   *
   * Tách hẳn khỏi `ask`: đường này gọi endpoint riêng, không stream, và có hai
   * kiểu kết quả — ảnh đã sửa, hoặc một câu hỏi ngược khi trợ lý chưa rõ ý.
   * Trường hợp hỏi ngược thì GIỮ NGUYÊN ảnh đính kèm để người dùng trả lời tiếp
   * mà không phải bấm đính kèm lại.
   */
  const suaAnh = async (yeuCau) => {
    const message = yeuCau.trim();
    if (!message || sending || !anhChinh) return;

    const id = `${Date.now()}-${Math.random()}`;
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: message },
      { id, role: 'assistant', content: '' },
    ]);
    setInput('');
    setSending(true);
    setBuoc('Đang xem ảnh và chỉnh sửa…');

    try {
      const ket_qua = await editImage(anhChinh, message, sessionRef.current);
      if (ket_qua.status === 'clarify') {
        capNhatTin(id, { content: ket_qua.question });
        return;
      }
      const anhMoi = `data:image/png;base64,${ket_qua.image_base64}`;
      const da_sua = ket_qua.object_edited ? `Mình đã chỉnh **${ket_qua.object_edited}** theo yêu cầu.` : 'Mình đã chỉnh xong.';
      capNhatTin(id, {
        // Nói thẳng chuyện lượt sau sẽ cộng dồn lên ảnh này. Không nói thì người
        // dùng gõ yêu cầu thứ hai và tưởng nó áp lên ảnh gốc — nhận về kết quả
        // khác hẳn mong đợi mà không hiểu vì sao.
        content: `${da_sua} Bấm vào ảnh để xem lớn hơn.\n\nLần sửa tiếp theo sẽ dựa trên **chính ảnh này**. Muốn làm lại từ ảnh gốc thì bấm "Dùng ảnh gốc" ở khung đính kèm.`,
        anh: anhMoi,
      });
      // GIỮ chế độ đính kèm và chuyển nguồn sang ảnh vừa sửa — đây là mặc định
      // sửa nối tiếp, người dùng chỉnh dần từng bước chứ hiếm khi xong một lượt.
      setAnhDaSua(anhMoi);
    } catch (error) {
      capNhatTin(id, { content: error.message, error: true });
    } finally {
      setSending(false);
      setBuoc('');
    }
  };

  /**
   * Bấm vào một ảnh trong khung chat: vừa phóng to, vừa lấy nó làm ảnh nguồn.
   *
   * Làm cả hai việc trong một cú bấm là có chủ ý. Người dùng đã yêu cầu bấm ảnh
   * thì phóng to, nay yêu cầu bấm ảnh thì chọn làm ngữ cảnh — tách thành hai
   * thao tác khác nhau sẽ phải thêm nút và bắt họ nhớ nút nào làm gì.
   *
   * Việc đổi ngữ cảnh KHÔNG âm thầm: ảnh đang được chọn có viền và nhãn "Đang
   * sửa ảnh này", nên nhìn là biết lượt sau sẽ áp lên tấm nào.
   *
   * Nhờ vậy quay lại ảnh của bước 2 rồi rẽ hướng khác là được — không phải làm
   * lại từ đầu chỉ vì bước 5 đi sai.
   */
  const chonAnhTuChat = (anh) => {
    setAnhPhongTo(anh);
    setAnhDaSua(anh);
    setDinhKemAnh(true);
  };

  const capNhatTin = (id, thayDoi) =>
    setMessages((prev) => prev.map((item) => (item.id === id ? { ...item, ...thayDoi } : item)));

  /** Bấm gửi: đang đính kèm ảnh thì đi đường sửa ảnh, không thì hỏi như thường. */
  const guiTin = (text) => (dinhKemAnh && anhChinh ? suaAnh(text) : ask(text));

  /** Mở chat rồi hỏi luôn — người dùng bấm một nút, không phải hai bước. */
  const phanTichCanDangXem = () => {
    if (!open) onToggle();
    ask(`Phân tích chi tiết căn ${maCanDangXem}`);
  };

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [messages, sending]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const ask = async (text) => {
    const message = text.trim();
    if (!message || sending) return;

    // history gửi lên là hội thoại TRƯỚC câu này. Bỏ bong bóng lỗi, và bỏ cả
    // bong bóng RỖNG — đó là chỗ chờ token của một lượt hỏng giữa chừng. Lõi AI
    // đặt `min_length=1` cho content nên gửi chuỗi rỗng là cả request bị 422,
    // tức một lần hỏng sẽ làm hỏng mọi lượt sau.
    const history = messages
      .filter((item) => !item.error && item.content)
      .slice(-MAX_HISTORY)
      .map(({ role, content }) => ({ role, content }));

    // Đánh dấu bong bóng bằng id tạo SẴN, không dùng chỉ số mảng. React chạy
    // hàm cập nhật state lúc nó muốn, nên gán chỉ số bên trong hàm đó là đọc
    // phải giá trị cũ — khi ấy mọi cập nhật sau đều không khớp dòng nào và
    // người dùng nhìn thấy một bong bóng rỗng vĩnh viễn.
    const id = `${Date.now()}-${Math.random()}`;
    const capNhat = (thayDoi) =>
      setMessages((prev) => prev.map((item) => (item.id === id ? { ...item, ...thayDoi } : item)));

    setMessages((prev) => [
      ...prev,
      { role: 'user', content: message },
      { id, role: 'assistant', content: '' },
    ]);
    setInput('');
    setSending(true);
    setBuoc('');
    setDangTraLoi(false);

    if (maCanDangXem) daMoiRef.current.add(maCanDangXem);

    try {
      await streamChatMessage(
        themNguCanh(message, maCanDangXem),
        history,
        (event) => {
          if (event.session_id && !sessionRef.current) sessionRef.current = event.session_id;
          if (event.type === 'token') {
            setDangTraLoi(true);
            setBuoc('');
            setMessages((prev) =>
              prev.map((item) =>
                item.id === id ? { ...item, content: item.content + event.content } : item,
              ),
            );
          } else if (event.type === 'route') {
            const mo_ta = moTaBuoc(event);
            if (mo_ta) setBuoc(mo_ta);
          } else if (event.type === 'error') {
            capNhat({ content: event.content, error: true });
          }
        },
        undefined,
        sessionRef.current,
      );
    } catch (error) {
      capNhat({ content: error.message, error: true });
    } finally {
      setSending(false);
      setBuoc('');
      setDangTraLoi(false);
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      guiTin(input);
    }
  };

  // Rời khỏi trang chi tiết căn thì không còn ảnh để đính kèm nữa.
  useEffect(() => {
    if (!maCanDangXem) setDinhKemAnh(false);
  }, [maCanDangXem]);

  // Lời mời phân tích nổi CẠNH nút chat chứ không nằm trong panel: đặt bên
  // trong thì chỉ ai đã mở chat mới thấy, mà người đang xem một căn thường
  // chưa mở. Một nút vừa mở chat vừa hỏi luôn.
  const loiMoi = moiPhanTich && (
    <div className="cw-moi" role="dialog" aria-label="Gợi ý từ trợ lý S">
      <button className="cw-moi-dong" aria-label="Đóng gợi ý" onClick={() => setBoQua(true)}>
        <CloseIcon />
      </button>
      <div className="cw-moi-ava">S</div>
      <p className="cw-moi-ten">{tieuDeCan(maCanDangXem, canDangXem)}</p>
      <p className="cw-moi-hoi">Bạn có muốn mình phân tích chi tiết căn này không?</p>
      <div className="cw-moi-nut">
        <button onClick={phanTichCanDangXem}>Phân tích chi tiết</button>
        <button className="phu" onClick={() => setBoQua(true)}>
          Để sau
        </button>
      </div>
    </div>
  );

  if (!open) {
    return (
      <>
        {loiMoi}
        <div className="fab">
          <button aria-label="Mở trợ lý S" onClick={onToggle}>
            S
          </button>
        </div>
      </>
    );
  }

  // Lớp phóng to nằm NGOÀI sidebar để phủ cả màn hình: sidebar chỉ rộng 1/3,
  // xem ảnh trong đó thì vẫn bé y như lúc chưa bấm.
  const lopPhongTo = anhPhongTo && (
    <div
      className="cw-lightbox"
      role="dialog"
      aria-label="Ảnh đã chỉnh sửa"
      onClick={() => setAnhPhongTo(null)}
    >
      <button aria-label="Đóng ảnh" onClick={() => setAnhPhongTo(null)}>
        <CloseIcon />
      </button>
      <img src={anhPhongTo} alt="Ảnh đã chỉnh sửa" onClick={(event) => event.stopPropagation()} />
    </div>
  );

  return (
    <>
      {lopPhongTo}
      <aside className="chat-sidebar" aria-label="Trợ lý S">
      <div className="cw-hd">
        <div className="ava">S</div>
        <div>
          <b>Trợ lý S</b>
          <span>SalesMate AI</span>
        </div>
        <div className="acts">
          <button aria-label="Thu gọn trợ lý" onClick={onToggle}>
            <CloseIcon />
          </button>
        </div>
      </div>

      <div className="cw-body" ref={bodyRef} aria-live="polite">
        <div className="cw-greet">
          Xin chào 👋 <b>Trợ lý S</b> giúp bạn tìm căn phù hợp, tra thông tin căn hộ và hỗ trợ tư
          vấn khách.
        </div>

        {messages.length === 0 && (
          <div className="qa">
            {(maCanDangXem ? goiYTheoCan(maCanDangXem) : QUICK_ASKS).map((text) => (
              <button key={text} onClick={() => ask(text)}>
                {text}
              </button>
            ))}
          </div>
        )}

        {/* Bỏ qua bong bóng còn rỗng: nó là chỗ chờ token đầu tiên, hiện ra
            trước thì người dùng thấy một ô trắng trống không hiểu là gì. Trong
            lúc đó đã có dòng trạng thái hoặc chấm nhấp nháy bên dưới. */}
        {messages
          .filter((item) => item.content)
          .map((item, index) => (
            <div
              key={item.id ?? index}
              className={item.role === 'user' ? 'cmsg u' : item.error ? 'cmsg a err' : 'cmsg a'}
            >
              {/* Tin của người dùng giữ nguyên văn — họ gõ gì hiện đúng thế.
                  Chỉ câu trả lời của trợ lý mới dựng markdown. */}
              {item.role === 'user' ? item.content : <CauTraLoi text={item.content} />}
              {item.anh && (
                <button
                  className={item.anh === anhChinh ? 'cmsg-anh dang-chon' : 'cmsg-anh'}
                  title="Bấm để xem lớn và chọn ảnh này làm ảnh sửa tiếp"
                  onClick={() => chonAnhTuChat(item.anh)}
                >
                  <img src={item.anh} alt="Ảnh đã chỉnh sửa, bấm để xem lớn và sửa tiếp" />
                  {item.anh === anhChinh && <span className="cmsg-anh-dau">Đang sửa ảnh này</span>}
                </button>
              )}
            </div>
          ))}

        {/* Chấm nhấp nháy chạy SUỐT từ lúc gửi tới lúc chữ đầu tiên hiện ra,
            kể cả trong lúc agent đang chọn tool. Trước đây dòng trạng thái thay
            chỗ chấm, nên mỗi lần đổi bước lại đứng im một nhịp — trông như treo.
            Nay hai thứ đi cùng nhau trong một bong bóng. */}
        {sending && !dangTraLoi && (
          <div className="ctyping">
            {buoc && <span className="ctyping-buoc">{buoc}</span>}
            <i />
            <i />
            <i />
          </div>
        )}
      </div>

      <div className="cw-foot">
        {dinhKemAnh && anhChinh && (
          <div className="cw-dinhkem">
            <img src={anhChinh} alt="" />
            <p>
              {anhDaSua ? (
                <>
                  Đang sửa tiếp trên <b>ảnh vừa chỉnh</b> của căn {maCanDangXem}.{' '}
                  <button className="cw-lienket" onClick={() => setAnhDaSua(null)}>
                    Dùng ảnh gốc
                  </button>
                </>
              ) : (
                <>
                  Đang đính kèm ảnh căn <b>{maCanDangXem}</b>. Nói rõ bạn muốn đổi chi tiết nào.
                </>
              )}
            </p>
            <button aria-label="Bỏ đính kèm ảnh" onClick={() => setDinhKemAnh(false)}>
              <CloseIcon />
            </button>
          </div>
        )}

        {dinhKemAnh && anhChinh && !sending && (
          <div className="qa qa-anh">
            {GOI_Y_SUA_ANH.map((text) => (
              <button key={text} onClick={() => guiTin(text)}>
                {text}
              </button>
            ))}
          </div>
        )}

        <div className="cw-inrow">
          {/* Chỉ bật khi đang mở một căn — không có ảnh thì không có gì để sửa. */}
          <button
            className={dinhKemAnh ? 'cw-them on' : 'cw-them'}
            aria-label={dinhKemAnh ? 'Bỏ đính kèm ảnh' : 'Đính kèm ảnh căn để nhờ sửa'}
            title={anhChinh ? 'Nhờ trợ lý sửa ảnh căn này' : 'Mở một căn hộ để dùng tính năng sửa ảnh'}
            disabled={!anhChinh || sending}
            onClick={() => setDinhKemAnh((bat) => !bat)}
          >
            +
          </button>
          <textarea
            ref={inputRef}
            rows={1}
            maxLength={2000}
            placeholder={dinhKemAnh ? 'Bạn muốn sửa chi tiết nào trong ảnh?' : 'Nhập câu hỏi cho Trợ lý S…'}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button
            className="cw-send"
            aria-label="Gửi"
            disabled={sending || !input.trim()}
            onClick={() => guiTin(input)}
          >
            <SendIcon />
          </button>
        </div>
      </div>
      </aside>
    </>
  );
}
