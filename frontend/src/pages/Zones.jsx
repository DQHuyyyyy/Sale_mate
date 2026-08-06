import { useEffect, useState } from 'react';
import { getZones } from '../api';
import ZoneList from '../components/ZoneList';

export default function Zones() {
  const [zones, setZones] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getZones()
      .then(setZones)
      .catch((zonesError) => setError(zonesError.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="wrap">
      <div className="page-head">
        <h1>Sơ đồ phân khu</h1>
        <p>Các phân khu trong dự án và những tòa thuộc từng khu.</p>
      </div>

      {error ? <div className="alert alert-error">{error}</div> : <ZoneList zones={zones} loading={loading} />}
    </div>
  );
}
