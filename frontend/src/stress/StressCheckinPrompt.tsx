import { Link } from "react-router";

// 채팅 응답이 정해진 동작을 돌려줄 때만 기록 화면 링크를 노출한다.
export default function StressCheckinPrompt({ action }: { action: unknown }) {
  if (action !== "open_stress_checkin") return null;
  return <Link className="primary-button" to="/records/stress" state={{ fromChat: true }}>오늘 스트레스 기록하기</Link>;
}
