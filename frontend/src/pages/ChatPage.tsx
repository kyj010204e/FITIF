
import { Link } from "react-router";

function ChatPage() {
  return (
    <main style={{ padding: "40px" }}>
      <h1>FITIF AI 건강 도우미</h1>

      <p>Gemma 4 연동을 준비 중입니다.</p>

      <Link to="/home">홈으로 돌아가기</Link>
    </main>
  );
}

export default ChatPage;
