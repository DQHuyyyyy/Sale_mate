import { Fragment, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { danhThucTroLy, getApartment, modifyApartmentImage, streamChatMessage } from '../api';
import { useAuth } from '../context/AuthContext';
import AnhPhongTo from './AnhPhongTo';
import CauTraLoi from './CauTraLoi';
import LoginModal from './LoginModal';
import { CloseIcon, ExpandIcon, PlusIcon, RobotMascot, SendIcon, WandIcon } from './Icons';

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
  if (c.wc != null) params.wc = String(c.wc);

  return Object.keys(params).length ? params : null;
}

/**
 * Đổi event tiến trình của lõi AI thành một câu người đọc hiểu được.
 *
 * `daTraTonKho` là việc đã xảy ra ở bước TRƯỚC. Cần truyền vào vì dòng trạng
 * thái chỉ có một chỗ hiện: mỗi event ghi đè event trước, nên người dùng chỉ
 * kịp thấy dòng CUỐI. Với câu so sánh căn hộ, dòng cuối là bước đọc tài liệu,
 * và nó khiến người xem tưởng giá với diện tích lấy từ tài liệu — ngược hẳn
 * nguyên tắc số một của dự án, vốn là số liệu căn KHÔNG BAO GIỜ lấy từ tài liệu.
 */
function moTaBuoc(event, daTraTonKho = false) {
  const { step, tools, found, action, tool, iteration } = event.data ?? {};

  if (step === 'router') return 'Đang xác định câu hỏi…';
  if (step === 'tools') {
    const ten = TEN_TOOL[(tools ?? [])[0]] ?? 'dữ liệu';
    return found ? `Đã tra ${ten} trong kho dữ liệu` : `Đã tra ${ten}, chưa thấy khớp`;
  }
  // CỐ Ý không nêu số đoạn. `rerank_top_n` cố định ở 5 nên con số đó LUÔN là 5
  // với mọi câu hỏi — nó nói về cấu hình chứ không nói gì về câu người dùng vừa
  // hỏi. Tệ hơn, 5 đoạn thường chỉ đến từ 2-3 tài liệu (mỗi tài liệu bị cắt
  // nhiều đoạn), nên "5 đoạn tài liệu" khiến người đọc tưởng có 5 nguồn.
  if (step === 'retrieve') {
    return daTraTonKho ? 'Đã tra tồn kho · đang đọc thêm các tài liệu…' : 'Đang đọc các tài liệu…';
  }

  // Vòng lặp agent: hiện thẳng lý do model tự nêu, đó chính là "suy luận" mà
  // người dùng muốn thấy. Chỉ ẩn nhánh clarify vì câu hỏi ngược sẽ hiện ngay
  // sau đó dưới dạng câu trả lời, nói trước là lặp.
  if (step === 'plan') return action === 'clarify' ? null : event.content || 'Đang cân nhắc bước tiếp theo…';
  if (step === 'act') {
    const ten = TEN_TOOL[tool] ?? tool;
    return `Đang tra ${ten}${iteration > 1 ? ` (lượt ${iteration})` : ''}…`;
  }

  // Nhánh leo thang: câu nhiều bước được chuyển sang orchestrator. Nói theo
  // VIỆC nó vừa làm chứ không nói tên luật hay tên model — người dùng không
  // quan tâm R1 là gì, họ chỉ cần biết trợ lý còn đang làm việc.
  if (step === 'orchestrate') {
    if (event.data?.loi) return 'Đã tra thêm nhưng chưa lấy được dữ liệu';
    const ten = (tools ?? []).map((t) => TEN_TOOL[t] ?? t);
    return ten.length ? `Đã tra thêm ${ten.join(', ')}` : 'Đang tra cứu kỹ hơn…';
  }

  return null;
}

/**
 * Dựng bong bóng cho một lỗi gọi API.
 *
 * 429 không phải lỗi kỹ thuật mà là THÔNG BÁO HỆ THỐNG: đã hết lượt hỏi miễn
 * phí của tài khoản khách. Nó được đánh dấu riêng (`hanMuc`) để dựng thành một
 * khối trông khác hẳn bong bóng trả lời nghiệp vụ.
 *
 * Vì sao phải khác hẳn: đợt test 08/09/2026 cho thấy khi câu chạm trần trông
 * giống một câu trả lời bình thường, sale đọc nó như "trợ lý không biết" chứ
 * không phải "đã hết lượt" — rồi mất niềm tin vào chất lượng bot. Chuyện đang
 * xảy ra và việc cần làm tiếp phải nhìn ra được bằng mắt, trước khi đọc chữ.
 *
 * Cũng không tô đỏ như `err`: người dùng không làm gì sai.
 */
function khungLoi(error) {
  if (error?.status === 429) {
    return { content: error.message, hanMuc: true, error: false };
  }
  return { content: error.message, error: true };
}

/**
 * Trợ lý S — sidebar bên phải, thu gọn thành nút tròn chữ "S".
 *
 * Mở được cho cả khách chưa đăng nhập. Backend giới hạn số lượt hỏi của khách
 * vãng lai; chạm trần thì trả 429 kèm LỜI MỜI liên hệ chuyên viên tư vấn, và
 * widget hiện nó như một tin nhắn bình thường — xem `khungLoi`.
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

  // Ảnh đang mở to. null = không mở.
  const [anhPhongTo, setAnhPhongTo] = useState(null);

  // Đăng nhập mở ngay trong widget, không đá người dùng sang trang khác — họ
  // đang giữa một cuộc hội thoại và quay lại là mất hết lịch sử trong state.
  //
  // `user` quyết định khối chạm trần có nút "Đăng nhập ngay" hay không: câu của
  // backend cho người ĐÃ đăng nhập nói về việc gửi quá nhanh, dựng nút đăng
  // nhập dưới nó là chỉ sai đường.
  const { user } = useAuth();
  const [moDangNhap, setMoDangNhap] = useState(false);

  // Lượt sửa tiếp theo lấy ảnh nào làm gốc: 'goc' = ảnh thật trong gallery,
  // 'ai' = ảnh AI vừa sinh. Chỉ là LỰA CHỌN MẶC ĐỊNH — người dùng đổi được.
  const [nguonSua, setNguonSua] = useState('goc');

  /**
   * Ảnh AI gần nhất của ĐÚNG căn đang xem, để sửa tiếp trên đó.
   *
   * Suy ra từ `messages` chứ không giữ state riêng. Bản trước giữ state rồi xoá
   * nó mỗi khi người dùng bấm sang ảnh khác trong gallery — chuỗi sửa mất hẳn,
   * không có đường quay lại, trong khi tấm ảnh đó vẫn nằm ngay trong khung chat
   * nhìn thấy được. Suy ra từ lịch sử thì nó còn đúng chừng nào bong bóng còn.
   *
   * Lọc theo mã căn: ảnh AI của căn khác không phải ảnh gốc hợp lệ cho căn này,
   * và server cũng sẽ từ chối vì cặp (ma_can, image_id) không khớp.
   */
  const anhAICuoi = (() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const tin = messages[i];
      if (tin.anhAI && tin.anhAICuaCan === maCanDangXem) return tin.anhAI;
    }
    return null;
  })();

  // Bấm sang ảnh khác trong gallery là một hành động RÕ RÀNG về ảnh: mặc định
  // quay về ảnh gốc. Nhưng chỉ đổi mặc định thôi — `anhAICuoi` vẫn còn đó nên
  // người dùng chọn lại "ảnh vừa tạo" bất cứ lúc nào.
  useEffect(() => {
    setNguonSua('goc');
  }, [maCanDangXem, chiSoAnhDangXem]);

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

  /**
   * Ô nhập cao dần theo số dòng người dùng gõ.
   *
   * `rows={1}` khoá chiều cao ở một dòng và không có gì thay đổi nó, nên câu dài
   * bị cuộn ngầm bên trong: khách gõ tới dòng thứ năm thì bốn dòng đầu biến mất
   * khỏi tầm nhìn, không đọc lại được để soát trước khi gửi. `max-height` trong
   * CSS vốn được viết cho một ô biết nở ra — chỉ là chưa ai viết phần nở.
   *
   * Phải đặt `auto` TRƯỚC khi đọc `scrollHeight`: giữ nguyên chiều cao cũ thì
   * `scrollHeight` không bao giờ nhỏ đi, và ô đã cao lên sẽ không co lại khi
   * người dùng xoá bớt chữ.
   *
   * `useLayoutEffect` chứ không phải `useEffect` — đo và đặt chiều cao xong
   * trước khi trình duyệt vẽ, nếu không mỗi lần xuống dòng là một nháy giật.
   * Phụ thuộc vào `input` nên chạy cho MỌI đường làm giá trị đổi: gõ tay, bấm
   * nút gợi ý, và cả lúc `setInput('')` sau khi gửi (ô co lại về một dòng).
   */
  useLayoutEffect(() => {
    const o = inputRef.current;
    if (!o) return undefined;

    const doLai = () => {
      o.style.height = 'auto';
      o.style.height = `${o.scrollHeight}px`;
    };
    doLai();

    // Sidebar rộng 33vw, nên kéo cửa sổ hẹp lại là chữ xuống dòng khác đi và
    // chiều cao vừa đo thành thiếu — đúng lại triệu chứng chữ bị khuất.
    window.addEventListener('resize', doLai);
    return () => window.removeEventListener('resize', doLai);
  }, [input, cheDo]);

  // Đánh thức lõi AI ngay khi mở widget, trước khi khách kịp gõ xong câu hỏi.
  // Chỉ bắn một lần mỗi phiên: lõi AI chỉ ngủ sau 15 phút không có lưu lượng,
  // mà mỗi câu hỏi đã tự làm mới đồng hồ đó. Bắn lại mỗi lần đóng/mở là gọi
  // thừa, và giữ service thức 24/7 thì tiêu hết 750 giờ instance của tháng.
  const daDanhThuc = useRef(false);
  useEffect(() => {
    if (!open || daDanhThuc.current) return;
    daDanhThuc.current = true;
    danhThucTroLy();
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

    // Đặt lại theo TỪNG LƯỢT hỏi. Dùng biến thường chứ không dùng state: nó chỉ
    // phục vụ việc dựng câu trạng thái ngay trong vòng lặp event này, và đẩy
    // lên state sẽ kéo theo một lần render thừa cho mỗi bước.
    let daTraTonKho = false;

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
            // Ghi nhận TRƯỚC khi dựng câu: bước `tools` chạy trước `retrieve`,
            // nên tới lượt retrieve thì cờ này đã đúng.
            if (event.data?.step === 'tools' && event.data?.found) daTraTonKho = true;

            const mo_ta = moTaBuoc(event, daTraTonKho);
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
            // Giữ NGUYÊN đối tượng citation, không rút lấy mỗi `title`: cần
            // `doc_id` để dựng đường dẫn tới trang tài liệu, và `kind` để biết
            // nhãn là mã căn hay tên tài liệu.
            // Ghi luôn MỐC nhận được. Giá và tình trạng căn đọc thẳng từ
            // Postgres ngay trong lượt này, nên đây là lúc dữ liệu được đọc —
            // sale cần biết con số trước mặt mới cỡ nào. Chấm mốc ở FE chứ
            // không xin backend vì `Citation` là hợp đồng đóng băng, không có
            // trường thời gian, và chênh lệch giữa hai đầu chỉ là mili giây.
            const nguon = (event.citations ?? []).filter((c) => c?.title);
            if (nguon.length) capNhat({ nguonThat: nguon, nguonLuc: Date.now() });
          } else if (event.type === 'done') {
            // Trợ lý hỏi ngược thì kèm sẵn vài phương án bấm được. Gắn vào
            // đúng bong bóng vừa trả lời, không để state riêng — người dùng
            // cuộn lên vẫn thấy các lựa chọn của lượt cũ.
            const chon = event.data?.options;
            if (Array.isArray(chon) && chon.length) capNhat({ options: chon });

            // Backend đã lọc nguồn và quyết định lượt này không được trích.
            // Phải nghe theo: dấu [Mã căn] model tự viết KHÔNG đi qua bộ lọc
            // nào, nên nó dựng lại đúng những nguồn backend vừa loại. Đã thấy
            // thật — trợ lý hỏi "bạn muốn lọc theo tiêu chí nào?" mà dưới đó
            // vẫn có "Nguồn: VOP758, VOP247, VOP619".
            if (event.data?.cho_trich_nguon === false) capNhat({ choTrichNguon: false });
          } else if (event.type === 'error') {
            capNhat({ content: event.content, error: true });
          }
        },
        undefined,
        sessionRef.current,
      );
    } catch (error) {
      capNhat(khungLoi(error));
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
      const ket_qua = await modifyApartmentImage({
        maCan: maCanDangXem,
        imageId: anh.id,
        yeuCau,
        // Sửa tiếp trên ảnh AI khi người dùng đang chọn vậy. Ảnh AI không được
        // lưu ở đâu cả nên server không tự tìm lại được — client gửi lại.
        anhNguon: nguonSua === 'ai' ? anhAICuoi : null,
      });
      // Vừa sinh xong thì mặc định lượt sau nối tiếp, để "đổi rèm sang xám" rồi
      // "bỏ cái bàn đi" cộng dồn lên nhau thay vì quay về ảnh gốc.
      setNguonSua('ai');
      setMessages((prev) =>
        prev.map((item) =>
          item.id === id
            ? {
                ...item,
                content: `Ảnh căn ${maCanDangXem} sau khi ${yeuCau}`,
                anhAI: ket_qua.anh,
                // Gắn mã căn để lượt sau biết ảnh này thuộc căn nào — ảnh AI
                // của căn khác không dùng làm gốc được.
                anhAICuaCan: maCanDangXem,
                options: goiYSauKhiSuaAnh(maCanDangXem),
              }
            : item,
        ),
      );
    } catch (error) {
      setMessages((prev) =>
        prev.map((item) => (item.id === id ? { ...item, ...khungLoi(error) } : item)),
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
              {/* Chạm trần hạn mức KHÔNG dựng thành bong bóng trả lời. Nó là
                  thông báo hệ thống: nền vàng, viền trái, biểu tượng cảnh báo —
                  khác hẳn cả bong bóng trắng của trợ lý lẫn bong bóng đỏ của
                  lỗi. Sale phân biệt được bằng mắt trước khi đọc chữ, đúng thứ
                  đợt test 08/09/2026 chỉ ra là đang thiếu.

                  Nút "Đăng nhập ngay" là hành động ĐÚNG duy nhất còn lại, và
                  chỉ hiện cho người chưa đăng nhập — xem `moDangNhap`. */}
              {item.hanMuc ? (
                <div className="cw-han-muc" role="status">
                  <p className="cw-han-muc-tin">
                    <span className="cw-han-muc-bieu-tuong" aria-hidden="true">
                      ⚠️
                    </span>
                    {item.content}
                  </p>
                  {!user && (
                    <button
                      type="button"
                      className="cw-han-muc-nut"
                      onClick={() => setMoDangNhap(true)}
                    >
                      Đăng nhập ngay
                    </button>
                  )}
                </div>
              ) : (
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
                      nguonLuc={item.nguonLuc}
                      choTrichNguon={item.choTrichNguon}
                      onChonCan={(ma) => navigate(`/apartments/${encodeURIComponent(ma)}`)}
                    />
                  )}

                  {/* Ảnh do AI dựng. Nhãn nằm NGAY TRÊN ảnh chứ không phải cuối
                      tin nhắn: người dùng chụp màn hình gửi cho khách thì nhãn
                      phải đi theo ảnh, nếu không đó thành ảnh thật của căn. */}
                  {item.anhAI && (
                    <figure className="cw-anh-ai">
                      {/* <button> chứ không phải onClick trên <img>: bàn phím và
                          trình đọc màn hình dùng được, và con trỏ đổi thành tay
                          nên người dùng biết là bấm được. */}
                      <button
                        type="button"
                        className="cw-anh-mo"
                        aria-label="Phóng to ảnh"
                        onClick={() => setAnhPhongTo({ src: item.anhAI, alt: item.content })}
                      >
                        <img src={item.anhAI} alt={item.content} />
                        <span className="cw-anh-zoom" aria-hidden="true">
                          <ExpandIcon />
                        </span>
                      </button>
                      <figcaption>Ảnh minh hoạ do AI tạo — không phải ảnh thật của căn</figcaption>
                    </figure>
                  )}
                </div>
              )}

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
            <div className="cw-chedo-dau">
              <WandIcon />
              <span>{TINH_NANG.find((tn) => tn.ma === cheDo)?.ten}</span>
              <button aria-label="Thoát chế độ" onClick={() => setCheDo(null)}>
                <CloseIcon />
              </button>
            </div>

            {/* Sửa trên ảnh nào là lựa chọn của NGƯỜI DÙNG, không phải suy đoán
                của giao diện. Bản trước tự quyết rồi chỉ ghi một dòng chữ:
                bấm sang ảnh khác trong gallery là chuỗi sửa mất hẳn, không có
                đường quay lại, dù tấm ảnh AI vẫn nằm ngay trong khung chat.

                Hiện cả hai nút kể cả khi chỉ có một lựa chọn hợp lệ — người
                dùng thấy được là có hai đường, và thấy mình đang ở đường nào. */}
            {cheDo === MODIFY && (
              <div className="cw-chedo-nguon" role="radiogroup" aria-label="Sửa trên ảnh nào">
                <button
                  role="radio"
                  aria-checked={nguonSua === 'goc'}
                  className={nguonSua === 'goc' ? 'on' : ''}
                  onClick={() => setNguonSua('goc')}
                >
                  Ảnh gốc{maCanDangXem && ` · ảnh ${chiSoAnhDangXem + 1}`}
                </button>
                <button
                  role="radio"
                  aria-checked={nguonSua === 'ai'}
                  className={nguonSua === 'ai' ? 'on' : ''}
                  disabled={!anhAICuoi}
                  title={anhAICuoi ? undefined : 'Chưa có ảnh AI nào của căn này'}
                  onClick={() => setNguonSua('ai')}
                >
                  Ảnh vừa tạo
                </button>
              </div>
            )}
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

      {anhPhongTo && (
        <AnhPhongTo
          src={anhPhongTo.src}
          alt={anhPhongTo.alt}
          ghiChu="Ảnh minh hoạ do AI tạo — không phải ảnh thật của căn"
          onDong={() => setAnhPhongTo(null)}
        />
      )}

      {/* Đăng nhập ngay trong widget. Đăng nhập xong `user` đổi, khối chạm trần
          tự bỏ nút đi, và lượt hỏi tiếp theo đã đi kèm token nên tính vào hạn
          mức nhân viên — người dùng không phải làm thêm bước nào. */}
      {moDangNhap && <LoginModal onClose={() => setMoDangNhap(false)} />}
    </aside>
  );
}
