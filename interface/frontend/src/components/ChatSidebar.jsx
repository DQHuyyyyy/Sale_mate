import { Fragment, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { getApartment, modifyApartmentImage, streamChatMessage } from '../api';
import CauTraLoi from './CauTraLoi';
import { CloseIcon, PlusIcon, RobotMascot, SendIcon, WandIcon } from './Icons';

// Gợi ý mở đầu. NHÃN và CÂU HỎI tách nhau có chủ đích: nút đọc gọn là
// "Ocean Park 1", nhưng gửi đúng chữ đó thì trợ lý trả lời về tiện ích chứ
// không liệt kê căn — đo được. Thêm chữ "Căn ở" là ra đúng danh sách căn.
const LOI_MOI_MO_DAU = 'Bạn muốn tìm căn ở khu vực nào?';
const GOI_Y_MO_DAU = [1, 2, 3].map((so) => ({
  nhan: `Ocean Park ${so}`,
  cau_hoi: `Căn ở Ocean Park ${so}`,
}));

// Backend chặn history ở 20 lượt (40 tin nhắn) và trả 422 nếu vượt. Lịch sử
// giữ nguyên trong sidebar suốt phiên nên sẽ chạm trần đó — cắt bớt trước khi
// gửi, giữ 30 tin gần nhất để còn biên an toàn.
const MAX_HISTORY = 30;

// Chế độ của ô nhập. Menu "+" mở ra các tính năng ngoài hỏi đáp; hiện mới có
// một, nhưng khai thành bảng để thêm mục sau chỉ là thêm một dòng.
const MODIFY = 'modify';
const TINH_NANG = [
  {
    ma: MODIFY,
    ten: 'Modify Object',
    mo_ta: 'Sửa nội thất trong ảnh đang xem',
    // Cần một ảnh cụ thể làm gốc, nên phải đang mở trang chi tiết một căn.
    can_anh: true,
    goi_y: 'Ví dụ: đổi sofa hiện tại thành màu nâu',
  },
];

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
const goiYTheoCan = (maCan) =>
  [
    `Phân tích chi tiết căn ${maCan}`,
    `Căn ${maCan} còn không, giá bao nhiêu?`,
    `Có căn nào tương tự ${maCan} không?`,
  ].map((cau) => ({ nhan: cau, cau_hoi: cau }));

/**
 * Bước tiếp sau khi sửa ảnh xong.
 *
 * Modify Object không đi qua lõi AI nên không có event `done` nào mang gợi ý về.
 * Dựng tại chỗ, ngắn thôi: khách vừa xem căn này trong đúng phong cách họ muốn —
 * đó là lúc gần quyết định nhất của cả phiên, đừng để màn hình dừng ở tấm ảnh.
 *
 * Cả ba câu đều tự chứa mã căn nên lõi AI tra được, giống luật của
 * `src/agents/suggest.py`.
 */
const goiYSauKhiSuaAnh = (maCan) => [
  `Đặt cọc giữ chỗ căn ${maCan}`,
  `Căn ${maCan} còn không, giá bao nhiêu?`,
  `Có căn nào tương tự ${maCan} không?`,
];

const TEN_TOOL = {
  inventory_lookup: 'thông tin căn',
  inventory_search: 'danh sách căn',
};

/**
 * Đổi tiêu chí `inventory_search` thành tham số URL của trang tìm kiếm.
 *
 * Trợ lý trả lời "có 12 căn từ 2 đến 3 tỷ" mà lưới bên ngoài vẫn hiện 97 căn
 * thì người dùng phải tự đối chiếu bằng mắt. Đẩy đúng bộ lọc đó lên URL để hai
 * bên nói cùng một tập căn.
 *
 * Chỉ lấy những tiêu chí trang tìm kiếm HIỂU được — nó không lọc theo hướng hay
 * view, đẩy lên cũng vô nghĩa. Trả null nghĩa là không có gì để đồng bộ.
 */
function boLocTuTieuChi(filters) {
  const c = filters?.inventory_search;
  if (!c) return null;

  const params = {};
  if (c.price_min != null) params.priceMin = String(c.price_min);
  if (c.price_max != null) params.priceMax = String(c.price_max);
  // "dưới 3 tỷ" loại luôn căn giá đúng 3 tỷ. Không truyền cờ này thì chat đếm
  // 21 căn còn lưới bên trái hiện 25, người dùng thấy ngay hai số vênh nhau.
  if (c.price_max_nghiem_ngat) params.priceMaxExclusive = 'true';
  if (c.subdivision) params.subdivision = c.subdivision;
  if (c.building) params.tower = c.building;
  if (c.unit_type) params.type = c.unit_type;

  return Object.keys(params).length ? params : null;
}

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
  // Lõi AI cấp ở lượt đầu, gửi lại các lượt sau để log gom về một phiên.
  const sessionRef = useRef(null);
  // Đã mời phân tích căn nào rồi — không mời lại căn đó trong cùng phiên.
  const daMoiRef = useRef(new Set());
  const [boQua, setBoQua] = useState(false);
  const bodyRef = useRef(null);
  const inputRef = useRef(null);

  // Menu "+" đang mở mục nào. null = chat thường.
  const [menuMo, setMenuMo] = useState(false);
  const [cheDo, setCheDo] = useState(null);

  // Đang xem căn nào thì đọc thẳng từ URL, không cần tầng state dùng chung.
  const navigate = useNavigate();
  const vitri = useLocation();
  const khop = vitri.pathname.match(/^\/apartments\/([^/]+)/);
  const maCanDangXem = khop ? decodeURIComponent(khop[1]) : null;
  // Ảnh đang xem cũng nằm trên URL — xem lý do ở đầu ApartmentDetail.jsx.
  const chiSoAnhDangXem = Math.max(0, Number(new URLSearchParams(vitri.search).get('anh') ?? 0) || 0);
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

            // Trợ lý vừa lọc theo tiêu chí nào thì lưới bên ngoài lọc theo đúng
            // tiêu chí đó. Chỉ làm khi tool THẬT SỰ tìm thấy căn — lọc ra danh
            // sách rỗng còn khó hiểu hơn là để nguyên.
            if (event.data?.step === 'tools' && event.data?.found) {
              const boLoc = boLocTuTieuChi(event.data.filters);
              if (boLoc) navigate({ pathname: '/tim-kiem', search: `?${new URLSearchParams(boLoc)}` });
            }
          } else if (event.type === 'sources') {
            // Nguồn THẬT do backend gom từ tool và truy hồi. Phải dùng nó chứ
            // không chỉ trông vào dấu [Mã căn] model tự viết trong câu trả lời:
            // model yếu bỏ qua luật trích nguồn, và production đang chạy
            // gpt-4o-mini nên dòng "Nguồn" biến mất hẳn trong khi local dùng
            // gpt-4o thì vẫn có. Nguồn là thứ chứng minh trợ lý không bịa —
            // không được phụ thuộc vào việc model có ngoan hay không.
            const ten = (event.citations ?? []).map((c) => c?.title).filter(Boolean);
            if (ten.length) capNhat({ nguonThat: ten });
          } else if (event.type === 'done') {
            // Trợ lý hỏi ngược thì kèm sẵn vài phương án bấm được. Gắn vào
            // đúng bong bóng vừa trả lời, không để state riêng — người dùng
            // cuộn lên vẫn thấy các lựa chọn của lượt cũ.
            const chon = event.data?.options;
            if (Array.isArray(chon) && chon.length) capNhat({ options: chon });
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

  /**
   * Modify Object — sửa ảnh đang xem theo yêu cầu bằng lời.
   *
   * Không đi qua lõi AI: `ChatRequest` là hợp đồng đóng băng, không có chỗ cho
   * `image_id`, và đây là thao tác một bước không cần router/retrieve/plan.
   */
  const suaAnh = async (text) => {
    const yeuCau = text.trim();
    if (!yeuCau || sending || !maCanDangXem) return;

    const anh = canDangXem?.images?.[chiSoAnhDangXem];
    if (!anh) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Căn này chưa có ảnh nào để sửa.', error: true },
      ]);
      return;
    }

    const id = `${Date.now()}-${Math.random()}`;
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: yeuCau },
      { id, role: 'assistant', content: '' },
    ]);
    setInput('');
    setCheDo(null);
    setSending(true);
    // Đo được 40-60 giây. Nói trước thời gian để người dùng không tưởng treo.
    setBuoc('Đang dựng ảnh, mất khoảng một phút…');
    setDangTraLoi(false);

    try {
      const ket_qua = await modifyApartmentImage({ maCan: maCanDangXem, imageId: anh.id, yeuCau });
      setMessages((prev) =>
        prev.map((item) =>
          item.id === id
            ? {
                ...item,
                content: `Ảnh căn ${maCanDangXem} sau khi ${yeuCau}`,
                anhAI: ket_qua.anh,
                options: goiYSauKhiSuaAnh(maCanDangXem),
              }
            : item,
        ),
      );
    } catch (error) {
      setMessages((prev) =>
        prev.map((item) => (item.id === id ? { ...item, content: error.message, error: true } : item)),
      );
    } finally {
      setSending(false);
      setBuoc('');
    }
  };

  /** Ô nhập dùng chung cho hỏi đáp và cho Modify Object — gửi đi đâu tuỳ chế độ. */
  const gui = () => (cheDo === MODIFY ? suaAnh(input) : ask(input));

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      gui();
    }
  };

  // Lời mời phân tích nổi CẠNH nút chat chứ không nằm trong panel: đặt bên
  // trong thì chỉ ai đã mở chat mới thấy, mà người đang xem một căn thường
  // chưa mở. Một nút vừa mở chat vừa hỏi luôn.
  const loiMoi = moiPhanTich && (
    <div className="cw-moi" role="dialog" aria-label="Gợi ý từ trợ lý S">
      <button className="cw-moi-dong" aria-label="Đóng gợi ý" onClick={() => setBoQua(true)}>
        <CloseIcon />
      </button>
      <div className="cw-moi-ava">
        <RobotMascot className="cw-moi-mk" />
      </div>
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
            <RobotMascot className="fab-mk" />
          </button>
        </div>
      </>
    );
  }

  return (
    <aside className="chat-sidebar" aria-label="Trợ lý S">
      <div className="cw-hd">
        <div className="ava">
          <RobotMascot className="cw-hd-mk" />
        </div>
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
          <>
            {/* Chỉ mời chọn khu vực khi người dùng CHƯA mở căn nào. Đang xem một
                căn mà hỏi ngược "khu vực nào" là bỏ qua thứ họ đang nhìn. */}
            {!maCanDangXem && <div className="cw-loi-moi">{LOI_MOI_MO_DAU}</div>}
            <div className="qa">
              {(maCanDangXem ? goiYTheoCan(maCanDangXem) : GOI_Y_MO_DAU).map((goi_y) => (
                <button key={goi_y.nhan} onClick={() => ask(goi_y.cau_hoi)}>
                  {goi_y.nhan}
                </button>
              ))}
            </div>
          </>
        )}

        {/* Bỏ qua bong bóng còn rỗng: nó là chỗ chờ token đầu tiên, hiện ra
            trước thì người dùng thấy một ô trắng trống không hiểu là gì. Trong
            lúc đó đã có dòng trạng thái hoặc chấm nhấp nháy bên dưới. */}
        {messages
          .filter((item) => item.content)
          .map((item, index) => (
            // Fragment chứ KHÔNG phải div bọc: `.cw-body` là flex column và
            // `.cmsg.u` canh phải bằng `align-self`, thứ chỉ có tác dụng lên
            // con TRỰC TIẾP của flex container. Bọc thêm một lớp div là bong
            // bóng của người dùng tụt về bên trái.
            <Fragment key={item.id ?? index}>
              <div
                className={item.role === 'user' ? 'cmsg u' : item.error ? 'cmsg a err' : 'cmsg a'}
              >
                {/* Tin của người dùng giữ nguyên văn — họ gõ gì hiện đúng thế.
                    Chỉ câu trả lời của trợ lý mới dựng markdown.

                    `onChonCan` biến trích nguồn dạng mã căn thành nút mở đúng
                    căn đó bên trái. Điều hướng để ở đây, không đưa vào
                    CauTraLoi: component đó chỉ dựng chữ, không nên biết tới
                    router. */}
                {item.role === 'user' ? (
                  item.content
                ) : (
                  <CauTraLoi
                    text={item.content}
                    nguonThat={item.nguonThat}
                    onChonCan={(ma) => navigate(`/apartments/${encodeURIComponent(ma)}`)}
                  />
                )}

                {/* Ảnh do AI dựng. Nhãn nằm NGAY TRÊN ảnh chứ không phải cuối
                    tin nhắn: người dùng chụp màn hình gửi cho khách thì nhãn
                    phải đi theo ảnh, nếu không đó thành ảnh thật của căn. */}
                {item.anhAI && (
                  <figure className="cw-anh-ai">
                    <img src={item.anhAI} alt={item.content} />
                    <figcaption>Ảnh minh hoạ do AI tạo — không phải ảnh thật của căn</figcaption>
                  </figure>
                )}
              </div>

              {/* Phương án chọn sẵn: vừa là đáp án cho câu hỏi ngược, vừa là
                  gợi ý hỏi tiếp sau một câu trả lời. Dùng lại đúng lớp `qa`
                  của gợi ý mở đầu — cùng ý nghĩa "bấm để hỏi luôn" thì nên
                  trông giống nhau. Ô nhập vẫn mở, ai muốn gõ tay vẫn gõ. */}
              {item.options?.length > 0 && (
                <>
                  <div className="cw-loi-moi">Bạn có thể hỏi tiếp:</div>
                  <div className="qa" role="group" aria-label="Gợi ý câu hỏi tiếp theo">
                    {item.options.map((text) => (
                      <button key={text} disabled={sending} onClick={() => ask(text)}>
                        {text}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </Fragment>
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
        {/* Menu tính năng. Mục cần ảnh mà chưa mở căn nào thì vẫn hiện nhưng
            khoá lại, kèm câu chỉ đường — ẩn hẳn thì người dùng không biết
            tính năng đó tồn tại. */}
        {menuMo && (
          <div className="cw-menu" role="menu">
            {TINH_NANG.map((tn) => {
              const khoa = tn.can_anh && !maCanDangXem;
              return (
                <button
                  key={tn.ma}
                  role="menuitem"
                  disabled={khoa}
                  onClick={() => {
                    setCheDo(tn.ma);
                    setMenuMo(false);
                    inputRef.current?.focus();
                  }}
                >
                  <WandIcon />
                  <span>
                    <b>{tn.ten}</b>
                    <i>{khoa ? 'Mở một căn hộ trước để dùng tính năng này' : tn.mo_ta}</i>
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {cheDo && (
          <div className="cw-chedo">
            <WandIcon />
            <span>
              {TINH_NANG.find((tn) => tn.ma === cheDo)?.ten}
              {maCanDangXem && ` · căn ${maCanDangXem}, ảnh ${chiSoAnhDangXem + 1}`}
            </span>
            <button aria-label="Thoát chế độ" onClick={() => setCheDo(null)}>
              <CloseIcon />
            </button>
          </div>
        )}

        <div className="cw-inrow">
          <button
            className={menuMo ? 'cw-plus on' : 'cw-plus'}
            aria-label="Tính năng khác"
            aria-expanded={menuMo}
            onClick={() => setMenuMo((truoc) => !truoc)}
          >
            <PlusIcon />
          </button>
          <textarea
            ref={inputRef}
            rows={1}
            maxLength={2000}
            placeholder={
              cheDo
                ? (TINH_NANG.find((tn) => tn.ma === cheDo)?.goi_y ?? 'Mô tả thay đổi bạn muốn…')
                : 'Nhập câu hỏi cho Trợ lý S…'
            }
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button className="cw-send" aria-label="Gửi" disabled={sending || !input.trim()} onClick={gui}>
            <SendIcon />
          </button>
        </div>
      </div>
    </aside>
  );
}
