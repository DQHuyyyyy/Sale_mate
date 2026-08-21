/**
 * Sơ đồ phân khu tương tác — dữ liệu dùng chung cho trang bản đồ và menu.
 *
 * Ranh giới sinh ra từ các file trong `so-do-phan-khu/`; file thiết kế là nguồn
 * sự thật. Sửa ranh giới thì sửa ở SVG rồi chép lại `d` sang đây, đừng nắn số
 * trực tiếp — không ai vẽ lại một chuỗi path bằng tay mà không lệch.
 *
 * `khung` phải khớp `viewBox` của SVG, và ảnh nền phải có **cùng tỉ lệ** với nó.
 * Không cần trùng số điểm ảnh: cả hai lớp đều giãn đúng bằng khung xem, nên chỉ
 * tỉ lệ mới quyết định vùng bấm có nằm đúng chỗ hay không. Ba dự án ba tỉ lệ
 * khác nhau, và Ocean Park 3 nằm DỌC — đừng viết cứng tỉ lệ nào vào CSS.
 */

// Vinhomes Ocean Park 1 — 17 phân khu, từ `so-do-phan-khu/Frame 1.svg`
const KHUNG_OP1 = { rong: 4096, cao: 2501 };

const VUNG_OP1 = [
  { ma: "the-paris", ten: "The Paris", d: "M462 904L459.5 924L648.5 1159.5L843.5 1002.5L746.5 909L677 819L462 904Z" },
  { ma: "the-zurich", ten: "The Zurich", d: "M844.5 1003L650 1161.5L787 1336.5L1004.5 1152L844.5 1003Z" },
  { ma: "the-london", ten: "The London", d: "M907.5 730L966 794.5L1064.5 706L1112 761L1165.5 717V706L1159 696.5H1151.5L1071 604.5L1076.5 598L1071 590.5L1056 584L1040 587C1009.67 611.833 941.2 665.8 910 683C878.8 700.2 892.333 721.5 903 730H907.5Z" },
  { ma: "the-beverly", ten: "The Beverly", d: "M1176 715.5L1009 852L1228.5 1105L1246 1113L1354 945V930L1176 715.5Z" },
  { ma: "the-zenpark", ten: "The Zenpark", d: "M1653.5 266L1502 333.5L1686.5 613.5L1830.5 507.5L1653.5 266Z" },
  { ma: "the-pavilion", ten: "The Pavilion", d: "M1980 72.5L1826.5 163L1990 391.5L2134.5 286L1980 72.5Z" },
  { ma: "lake-side", ten: "Lakeside", d: "M2097.5 0.5L1995 61.5L2135.5 258.5H2157L2366.5 95.5V71L2269.5 0.5H2097.5Z" },
  { ma: "sapphire1", ten: "Sapphire 1", d: "M1188.5 1269.5L1180 1229.5L1340 961L1363 952.5H1381L1538 1095L1588 1065.5L1641.5 1044.5L1677 1034L1699 1013L1724 961L1927 1077L1914.5 1102L1890.5 1087.5L1630 1513.5L1613 1520.5L1188.5 1269.5Z" },
  { ma: "sapphire2", ten: "Sapphire 2", d: "M1225.5 1610L1105 1716L1536.5 2224.5L1863 1675L1356 1376.5L1225.5 1610Z" },
  { ma: "masteri-waterfront", ten: "Masteri Waterfront", d: "M1885 1096L1629 1521.5L1819.5 1643L1837 1648L1860 1643L1878 1612.5H1889.5L2052.5 1350L2046.5 1344L2070.5 1306V1287.5L1931.5 1134.5L1913.5 1103L1885 1096Z" },
  { ma: "ngoc-trai", ten: "Ngọc Trai", d: "M2160.5 507.5L1891 706.5L1901.5 763L1973.5 867.5L1992 929.5L1973.5 986L1959.5 1039L2282 1463L2315 1481.5L2378 1504H2412.5L2529 1423.5L2594.5 1432L2632 1394.5V1341L2726.5 1264L2690.5 1125L2632 1029L2507 938L2356 728.5L2320 706.5L2210 524.5L2160.5 507.5Z" },
  { ma: "the-bayfront", ten: "The Bayfront", d: "M1781.5 743L1695 628L2153 293.5L2238 415.5L1781.5 743Z" },
  { ma: "bien-ho", ten: "Biển hồ", d: "M2390.5 117L2322 167.5V187.5L2407 304L2429 307.5L2531.5 230.5V216L2413.5 121L2390.5 117Z" },
  { ma: "the-senique", ten: "The Senique Hanoi", d: "M2539 239L2430 312.5L2424.5 322L2421.5 336L2585.5 559.5L2602 571H2613.5H2623L2807 433L2567.5 239H2539Z" },
  { ma: "sao-bien", ten: "Sao Biển", d: "M3063.5 634L2645.5 944.5L3141.5 1330.5L3297 1143L3594 1365.5L3749.5 1172.5L3063.5 634Z" },
  { ma: "hai-au", ten: "Hải Âu", d: "M2915 2309L2575.5 2111.5L2694.5 1912L2755.5 1812L2807 1743L2895.5 1659L2993.5 1609.5L3088.5 1574L3170.5 1556.5H3841.5L3946 1646.5L3814 1984L3788.5 2006.5H3748H3552H3439.5L3376.5 2019.5L3272 2039L3170.5 2076L3098.5 2126L3035.5 2172.5L2976 2233.5L2915 2309Z" },
  { ma: "san-ho", ten: "San Hô", d: "M2028 1487L1895.5 1701.5L2490 2051L2616.5 1841.5L2028 1487Z" },
];

// Vinhomes Ocean Park 2 — 9 phân khu, từ `so-do-phan-khu/vin2.svg`
const KHUNG_OP2 = { rong: 4096, cao: 2587 };

const VUNG_OP2 = [
  { ma: "co-xanh", ten: "Cỏ Xanh", d: "M992.5 608L497.5 819L815 1576.5L1314 1364.5L992.5 608Z" },
  { ma: "hai-au-2", ten: "Hải Âu", d: "M1317 1375L819.5 1587L1008.5 2029L1507 1817L1317 1375Z" },
  { ma: "dao-dua", ten: "Đảo Dừa", d: "M1806.5 1717L993.5 2064.5C1011.5 2112.67 1054.3 2218.3 1081.5 2255.5C1108.7 2292.7 1145.17 2312.67 1160 2318L1310.5 2342.5L1571.5 2326.5L1790.5 2253.5L1875 2273L1806.5 1717Z" },
  { ma: "cha-la", ten: "Chà Là", d: "M3214 1840L2728 1651L2482 2275L2971.5 2464L3214 1840Z" },
  { ma: "ngoc-trai", ten: "Ngọc Trai", d: "M2660.5 1356.5L3277.5 1092L3510.5 1662.5L3296 1815.5L2760.5 1612.5L2660.5 1356.5Z" },
  { ma: "sao-bien", ten: "Sao Biển", d: "M1274.5 436L1000.5 553.5L1105.5 813.5L1356 706.5L1697.5 1521L1739.5 1505L1811 1673.5L2047 1570.5L1544.5 390.5L1298.5 496L1274.5 436Z" },
  { ma: "kinh-do-anh-sang", ten: "Kinh Đô Ánh Sáng", d: "M1898 490L1648 591L2055 1564.5L2311.5 1459L1898 490Z" },
  { ma: "san-ho2", ten: "San Hô", d: "M2373.5 284L1932 474L2357 1459.5L2798.5 1276L2373.5 284Z" },
  { ma: "cong-vien", ten: "Công viên", d: "M2769.5 276L2441.5 414L2726 1086.5L3052 944L2769.5 276Z" },
];

// Vinhomes Ocean Park 3 — 8 phân khu, từ `so-do-phan-khu/vin3.svg`
const KHUNG_OP3 = { rong: 3420, cao: 4096 };

const VUNG_OP3 = [
  { ma: "hai-dang", ten: "Hải Đăng", d: "M3008 465.5L2769 323L2741 404.5L2652.5 371L2500 826L2527.5 839L2515 869.5L2561 889.5L2500 1070L2469.5 1085.5L2395.5 983.5L1948.5 1344.5L2159.5 1570.5L2251 1372.5L2192.5 1291L2451.5 1085.5L2327 1398L2469.5 1446L2665 930.5H2843L3008 465.5Z" },
  { ma: "anh-duong", ten: "Ánh Dương", d: "M2105.5 2392C2107.1 2390.4 2236.83 2077.67 2301.5 1921.5L2209 2087.5L2159 2143L2105.5 2185.5L2026 2231.5L1331.5 2543.5L1317 2586L1483 2957.5L2244 2621L2146 2392C2131.83 2392.67 2103.9 2393.6 2105.5 2392Z" },
  { ma: "pho-bien", ten: "Phố Biển", d: "M2246.5 2619.5L2066 2701.5L2129.5 2844.5L2029 2892.5L2302 3481.5L2909.5 3206.5L2841 3062L2514 3206.5L2246.5 2619.5Z" },
  { ma: "vinh-thien-duong", ten: "Vịnh Thiên Đường", d: "M1954 2747.5L1488.5 2961.5L1829 3705L2298.5 3485L1954 2747.5Z" },
  { ma: "thoi-dai", ten: "Thời Đại", d: "M1447 2975L1184 3089L1447 3680.5L1296.5 3755L1164 3461.5L1048.5 3519.5L1007.5 3408.5L986 3417.5L1135 3845L1459 3766L1492.5 3872L1527.5 3860V3834L1789 3720L1447 2975Z" },
  { ma: "vinh-tay", ten: "Vịnh Tây", d: "M384.5 2899.5V2749L999 2699L1238.5 2586L1278.5 2601L1447 2970.5L922 3213L774 2879L513 2899.5H384.5Z" },
  { ma: "dao-ngoc", ten: "Đảo Ngọc", d: "M1003 2682.5L383.5 2732L374.5 2420L463 2087.5L682.5 2126.5L890 2192L1022 2113.5L1247 2518.5L1229.5 2574L1003 2682.5Z" },
  { ma: "vinh-xanh", ten: "Vịnh Xanh", d: "M972 1936L976.5 1901.5L1493.5 2000.5L1683.5 2036.5L1834 2044.5L1941.5 2036.5L2037 2008.5L2131 1959.5L2207.5 1908L2271.5 1833L2295.5 1817.5L2229.5 2034.5L2186.5 2107L2085 2191L1326 2536.5L1265 2520L1036 2112V2088L979.5 1979.5L972 1936Z" },
];

/**
 * Ba dự án thành phần của Ocean City, theo thứ tự hiện trên menu.
 *
 * Một danh sách duy nhất cho cả menu thả xuống lẫn trang sơ đồ: thêm một sơ đồ
 * chỉ là điền `anh` + `vung` ở đây, không phải sửa menu, sửa route rồi sửa tiếp
 * trang — đúng ba chỗ dễ quên một.
 *
 * `vung` rỗng nghĩa là CHƯA có file thiết kế, và trang nói thẳng điều đó thay vì
 * hiện một khung trắng. Đừng lấy tạm sơ đồ của khu khác cho đủ chỗ.
 */
export const DU_AN_SO_DO = [
  {
    ma: 'op1',
    ten: 'Vinhomes Ocean Park 1',
    anh: '/media/so-do-ocean-park-1.jpg',
    khung: KHUNG_OP1,
    vung: VUNG_OP1,
  },
  {
    ma: 'op2',
    ten: 'Vinhomes Ocean Park 2',
    anh: '/media/so-do-ocean-park-2.jpg',
    khung: KHUNG_OP2,
    vung: VUNG_OP2,
  },
  {
    ma: 'op3',
    ten: 'Vinhomes Ocean Park 3',
    anh: '/media/so-do-ocean-park-3.jpg',
    khung: KHUNG_OP3,
    vung: VUNG_OP3,
  },
];

export function duongDanSoDo(ma) {
  return `/so-do-phan-khu/${ma}`;
}

export function timDuAn(ma) {
  return DU_AN_SO_DO.find((duAn) => duAn.ma === ma) ?? null;
}
