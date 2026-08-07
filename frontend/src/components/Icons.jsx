// Icon lấy từ mockup home.html. Dùng currentColor để thừa kế màu chỗ đặt.
const stroke = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
};

export const LogoMark = (props) => (
  <svg viewBox="0 0 40 40" fill="none" {...props}>
    <path
      d="M6 30V14l14-8 14 8v16"
      stroke="currentColor"
      strokeWidth="3.2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M15 30v-8h10v8"
      stroke="currentColor"
      strokeWidth="3.2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

export const SearchIcon = (props) => (
  <svg viewBox="0 0 24 24" {...stroke} {...props}>
    <circle cx="11" cy="11" r="7" />
    <path d="M21 21l-4.3-4.3" />
  </svg>
);

export const MapIcon = (props) => (
  <svg viewBox="0 0 24 24" {...stroke} {...props}>
    <path d="M9 3l6 2 6-2v16l-6 2-6-2-6 2V5z" />
    <path d="M9 3v16M15 5v16" />
  </svg>
);

export const ClockIcon = (props) => (
  <svg viewBox="0 0 24 24" {...stroke} {...props}>
    <path d="M12 8v4l3 2" />
    <circle cx="12" cy="12" r="9" />
  </svg>
);

export const UsersIcon = (props) => (
  <svg viewBox="0 0 24 24" {...stroke} {...props}>
    <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13A4 4 0 0116 11" />
  </svg>
);

export const ChartIcon = (props) => (
  <svg viewBox="0 0 24 24" {...stroke} {...props}>
    <path d="M3 3v18h18" />
    <path d="M18 9l-5 5-3-3-4 4" />
  </svg>
);

export const HouseIcon = (props) => (
  <svg viewBox="0 0 24 24" {...stroke} {...props}>
    <path d="M3 21h18M5 21V9l7-5 7 5v12M9 21v-6h6v6" />
  </svg>
);

export const FileIcon = (props) => (
  <svg viewBox="0 0 24 24" {...stroke} {...props}>
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
    <path d="M14 2v6h6M12 12v6M9 15h6" />
  </svg>
);

export const UserIcon = (props) => (
  <svg viewBox="0 0 24 24" {...stroke} {...props}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21v-1a6 6 0 016-6h4a6 6 0 016 6v1" />
  </svg>
);

export const LogoutIcon = (props) => (
  <svg viewBox="0 0 24 24" {...stroke} {...props}>
    <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" />
  </svg>
);

export const BurgerIcon = (props) => (
  <svg viewBox="0 0 24 24" {...stroke} {...props}>
    <path d="M3 6h18M3 12h18M3 18h18" />
  </svg>
);

export const AreaIcon = (props) => (
  <svg viewBox="0 0 24 24" {...stroke} {...props}>
    <path d="M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z" />
  </svg>
);

export const CompassIcon = (props) => (
  <svg viewBox="0 0 24 24" {...stroke} {...props}>
    <path d="M12 2v20M2 12h20" />
  </svg>
);

export const ExpandIcon = (props) => (
  <svg viewBox="0 0 24 24" {...stroke} {...props}>
    <path d="M8 3H5a2 2 0 00-2 2v3M16 3h3a2 2 0 012 2v3M8 21H5a2 2 0 01-2-2v-3M16 21h3a2 2 0 002-2v-3" />
  </svg>
);

export const CloseIcon = (props) => (
  <svg viewBox="0 0 24 24" {...stroke} {...props}>
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
);

export const SendIcon = (props) => (
  <svg viewBox="0 0 24 24" {...stroke} {...props}>
    <path d="M22 2L11 13M22 2l-7 20-4-9-9-4z" />
  </svg>
);

export const BackIcon = (props) => (
  <svg viewBox="0 0 24 24" {...stroke} {...props}>
    <path d="M19 12H5M12 19l-7-7 7-7" />
  </svg>
);

export const ZoneIcon = (props) => (
  <svg viewBox="0 0 24 24" {...stroke} strokeWidth="1.6" {...props}>
    <path d="M3 21h18M5 21V7l7-4 7 4v14M9 21v-5h6v5" />
  </svg>
);
