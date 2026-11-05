from fastapi import APIRouter, Depends, Header, HTTPException
from ocr_loader import connect, load_ocr_result

router = APIRouter()


# member_id를 얻는 곳은 여기 한 군데. 로그인이 붙으면 이 함수만 토큰에서 꺼내도록 바꾸면 됨
def get_current_member_id(x_member_id: int = Header(...)) -> int:
    return x_member_id


@router.post("/ocr/save")
def save_ocr(
    data: dict,
    dry_run: bool = True,  # 실제 저장은 ?dry_run=false
    member_id: int = Depends(get_current_member_id),
):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM member WHERE member_id = %s", (member_id,))
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="존재하지 않는 member_id입니다.")

        return load_ocr_result(conn, member_id, data, dry_run=dry_run)
    except (ValueError, KeyError) as e:
        # 검수 미완료, 코드 매칭 실패, JSON 필드 누락 등
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()