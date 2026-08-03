import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { calendarApi } from "../api/calendar";

export default function CalendarIndexRedirect() {
  const [target, setTarget] = useState<string | null>(null);

  useEffect(() => {
    calendarApi.datesWithData().then((dates) => {
      const latest = dates.length ? dates[dates.length - 1] : null;
      if (latest) {
        const [y, m] = latest.split("-");
        setTarget(`/calendar/${Number(y)}/${Number(m)}`);
      } else {
        const now = new Date();
        setTarget(`/calendar/${now.getFullYear()}/${now.getMonth() + 1}`);
      }
    });
  }, []);

  if (!target) return null;
  return <Navigate to={target} replace />;
}
