import { useEffect, useState } from "react";
import { daysApi } from "../api/days";
import type { Strategy } from "../api/types";

export function useStrategies() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  useEffect(() => {
    daysApi.strategies().then(setStrategies);
  }, []);
  return strategies;
}
