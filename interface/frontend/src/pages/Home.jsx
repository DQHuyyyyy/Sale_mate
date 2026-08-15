import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { MapIcon, SearchIcon } from '../components/Icons';

/**
 * Trang chủ — giới thiệu đại đô thị Ocean City và ba dự án thành phần.
 *
 * Mọi con số ở đây lấy nguyên từ bộ tài liệu trong `data/raw/knowledge/`
 * (nguồn market.vinhomes.vn) — cùng đúng bộ tài liệu mà trợ lý S trích dẫn.
 * Không tự chế thêm số: khách đọc trang này rồi hỏi trợ lý phải nghe một
 * con số duy nhất, không phải hai.
 */

const TONG_QUAN = [
  { so: '1.200 ha', nhan: 'Quy mô Ocean City' },
  { so: '3', nhan: 'Dự án thành phần' },
  { so: 'Vinhomes', nhan: 'Chủ đầu tư' },
  { so: 'Phía Đông Hà Nội', nhan: 'Vị trí' },
];

const DU_AN = [
  {
    ma: 'op1',
    ten: 'Vinhomes Ocean Park 1',
    anh: '/media/ocean-park-1.jpg',
    mo_ta:
      'Đại đô thị đầu tiên của Ocean City, nằm tại xã Gia Lâm, Hà Nội — cửa ngõ phía Đông ' +
      'thành phố, tiếp giáp nhiều tuyến giao thông quan trọng. Khu đô thị đã hoàn thiện và ' +
      'đang vận hành với cộng đồng cư dân đông đúc.',
    thong_so: [
      ['Tổng diện tích', '420 ha'],
      ['Mật độ xây dựng', '19%'],
      ['Quy mô', '66 tòa căn hộ · 2.390 căn thấp tầng · 1 tòa văn phòng'],
      ['Khởi công', 'Quý II/2018'],
      ['Tiến độ', 'Đã hoàn thiện'],
      ['Sở hữu', 'Lâu dài hoặc 50 năm'],
    ],
    diem_nhan: [
      '5 khu: The Sapphire, The Ocean View, The Metropolitan, Masteri Collection, The Senique Hanoi.',
      'Căn hộ dòng Sapphire, Ruby, Diamond — diện tích 26,6 đến 106,3 m², từ studio đến 3 phòng ngủ.',
      'Biển hồ nước mặn 6,1 ha và hồ nước ngọt trải cát trắng nhân tạo 24,5 ha, gấp đôi diện tích hồ Hoàn Kiếm.',
      'Trường học các cấp, cơ sở y tế và Đại học VinUni tiêu chuẩn quốc tế ngay trong khu đô thị.',
    ],
    vi_tri: '2 phút tới cao tốc Hà Nội – Hải Phòng · 15 phút tới khu vực Hồ Gươm.',
  },
  {
    ma: 'op2',
    ten: 'Vinhomes Ocean Park 2',
    anh: '/media/ocean-park-2.jpg',
    mo_ta:
      '"Quận ăn, quận chơi" của Ocean City. Điểm khác biệt nằm ở khả năng tạo dòng người thật ' +
      'và hoạt động thương mại thật — K-Town, Little Hong Kong, Kingdom Avenue và quảng trường ' +
      'Kinh Đô Ánh Sáng hình thành kinh tế đêm, hút khách liên tục thay vì chỉ đông cư dân nội khu.',
    thong_so: [
      ['Tổng diện tích', '458 ha'],
      ['Mật độ xây dựng', '30%'],
      ['Quy mô', '24 tòa căn hộ · 12.841 căn thấp tầng'],
      ['Khởi công', 'Quý III/2021'],
      ['Tiến độ', 'Đã hoàn thành'],
      ['Sở hữu', 'Lâu dài hoặc 50 năm'],
    ],
    diem_nhan: [
      '8 khu chức năng với nhiều phong cách kiến trúc: Venice, Địa Trung Hải, Đông Dương, Pháp cổ.',
      'Royal Wave Park 18 ha, hồ nước mặn Laguna 9,3 ha, Silk Park dài 2,6 km.',
      'Hệ tiện ích đồng bộ Vincom, Vinschool, Vinmec, công viên chủ đề và phố thương mại.',
      'Hưởng lợi từ cao tốc Hà Nội – Hải Phòng, Vành đai 3.5, cầu Vĩnh Tuy 2, cầu Trần Hưng Đạo.',
    ],
    vi_tri: '3 phút tới Ocean Park 1 · 10 phút tới cầu Vĩnh Tuy · 20 phút tới Hồ Hoàn Kiếm.',
  },
  {
    ma: 'op3',
    ten: 'Vinhomes Ocean Park 3',
    anh: '/media/ocean-park-3.jpg',
    mo_ta:
      'Được định vị là "Uptown" của Ocean City — mảnh ghép hoàn thiện hệ sinh thái sống, ' +
      'nghỉ dưỡng và thương mại phía Đông Hà Nội. Dự án ôm trọn sông Bắc Hưng Hải, có không ' +
      'gian sống ven sông hiếm thấy so với các đại đô thị gần thủ đô.',
    thong_so: [
      ['Tổng diện tích', '294 ha'],
      ['Mật độ xây dựng', '35%'],
      ['Quy mô', '8.458 căn thấp tầng'],
      ['Khởi công', 'Quý II/2022'],
      ['Tiến độ', 'Đang xây dựng'],
      ['Sở hữu', 'Lâu dài hoặc 50 năm'],
    ],
    diem_nhan: [
      'VinWonder Water Park 12 ha, Tropical Lagoon 2,8 ha, biển nước mặn bốn mùa Four Seasons.',
      'Marina Square sức chứa 3.000 người và 11 công viên chủ đề.',
      'Bể bơi phong cách resort, phong cách Olympics, quảng trường sự kiện liên hoàn.',
      'Giao lộ cao tốc Hà Nội – Hải Phòng với Vành đai 3.5, kết nối trực tiếp Vành đai 4 theo quy hoạch.',
    ],
    vi_tri: 'Hơn 20 phút tới hồ Hoàn Kiếm qua cầu Thanh Trì và cầu Vĩnh Tuy.',
  },
];

/**
 * Video giới thiệu — tự phát khi cuộn tới, lặp vô hạn, không có thanh điều khiển.
 *
 * `muted` là bắt buộc chứ không phải lựa chọn: trình duyệt chặn tự phát video
 * có tiếng khi người dùng chưa chạm vào trang. Thiếu nó thì `play()` bị từ chối
 * và video đứng im ở khung poster.
 *
 * Ra khỏi tầm nhìn thì dừng — cuộn xuống mấy khối dự án bên dưới mà video vẫn
 * chạy ngầm là phí pin và băng thông.
 */
function VideoGioiThieu() {
  const oVideo = useRef(null);

  useEffect(() => {
    const video = oVideo.current;
    if (!video) return undefined;

    const theoDoi = new IntersectionObserver(
      ([muc]) => {
        if (muc.isIntersecting) {
          // play() trả Promise và bị từ chối khi trình duyệt chặn tự phát —
          // nuốt lỗi, không để nó nổi lên thành unhandled rejection.
          video.play().catch(() => {});
        } else {
          video.pause();
        }
      },
      { threshold: 0.35 },
    );

    theoDoi.observe(video);
    return () => theoDoi.disconnect();
  }, []);

  return (
    <section className="hm-video">
      <video
        ref={oVideo}
        muted
        loop
        playsInline
        preload="metadata"
        poster="/media/ocean-park-tong-quan.jpg"
        src="/media/ocean-park-gioi-thieu.mp4"
      >
        Trình duyệt không phát được video này. Tải trực tiếp tại{' '}
        <a href="/media/ocean-park-gioi-thieu.mp4">liên kết video giới thiệu</a>.
      </video>
    </section>
  );
}

function KhoiDuAn({ duAn, dao }) {
  return (
    <section className={dao ? 'hm-proj hm-proj-dao' : 'hm-proj'} id={duAn.ma}>
      <div className="hm-proj-anh">
        <img src={duAn.anh} alt={duAn.ten} loading="lazy" />
      </div>

      <div className="hm-proj-noi-dung">
        <h2>{duAn.ten}</h2>
        <p className="hm-proj-mo-ta">{duAn.mo_ta}</p>

        <dl className="hm-specs">
          {duAn.thong_so.map(([nhan, gia_tri]) => (
            <div key={nhan}>
              <dt>{nhan}</dt>
              <dd>{gia_tri}</dd>
            </div>
          ))}
        </dl>

        <ul className="hm-diem-nhan">
          {duAn.diem_nhan.map((diem) => (
            <li key={diem}>{diem}</li>
          ))}
        </ul>

        <p className="hm-vi-tri">
          <MapIcon />
          {duAn.vi_tri}
        </p>
      </div>
    </section>
  );
}

export default function Home() {
  return (
    <>
      {/* Ảnh key visual đã có sẵn chữ trong thiết kế — không phủ thêm tiêu đề
          lên trên, phần dẫn nhập để xuống khối text ngay dưới. */}
      <div className="hm-hero">
        {/* width/height là kích thước thật của file. CSS vẫn quyết định bề rộng
            hiển thị; hai thuộc tính này chỉ để trình duyệt biết tỉ lệ mà chừa
            sẵn chỗ, tránh cả trang nhảy một nhịp khi ảnh tải xong. */}
        <img
          src="/media/ocean-park-tong-quan.jpg"
          alt="Vinhomes Ocean Park ví như quận Ocean, the new Hanoi"
          width={2880}
          height={1360}
        />
      </div>

      <div className="wrap">
        <section className="hm-intro">
          <span className="hm-eyebrow">Tổng quan dự án</span>
          <h1>Vinhomes Ocean Park — thành phố biển hồ phía Đông Hà Nội</h1>
          <p>
            Ocean City là quần thể đại đô thị quy mô 1.200 ha do Vinhomes phát triển tại cửa ngõ
            phía Đông Hà Nội, gồm ba dự án thành phần Ocean Park 1, 2 và 3. Điểm chung của cả ba là
            hệ thống biển hồ nhân tạo, công viên chủ đề và tiện ích nội khu khép kín — trường học,
            y tế, thương mại — trong bán kính đi bộ.
          </p>

          <div className="hm-stats">
            {TONG_QUAN.map((muc) => (
              <div className="hm-stat" key={muc.nhan}>
                <strong>{muc.so}</strong>
                <span>{muc.nhan}</span>
              </div>
            ))}
          </div>

          <div className="hm-cta">
            <Link className="btn btn-primary" to="/tim-kiem">
              <SearchIcon />
              Tìm căn hộ đang mở bán
            </Link>
            <Link className="btn btn-ghost" to="/zones">
              <MapIcon />
              Xem sơ đồ phân khu
            </Link>
          </div>
        </section>

        <VideoGioiThieu />

        {DU_AN.map((duAn, chiSo) => (
          <KhoiDuAn key={duAn.ma} duAn={duAn} dao={chiSo % 2 === 1} />
        ))}
      </div>
    </>
  );
}
