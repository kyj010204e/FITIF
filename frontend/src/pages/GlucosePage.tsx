import GlucoseTrendChart from "../components/GlucoseTrendChart";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import { Link } from "react-router";
import {
  ArrowLeft,
  Droplets,
  Plus,
  RefreshCw,
  Clock3,
  ChartNoAxesColumn,
  Pencil,
  Trash2,
} from "lucide-react";

import { useAuth } from "../auth/AuthProvider";
import "./GlucosePage.css";

// ==============================================
// 1. 데이터 타입 정의
// ==============================================

type MeasurementContext =
  | "fasting"
  | "before_meal"
  | "after_meal"
  | "bedtime"
  | "other"
  | "unknown";

type MeasurementMethod =
  | "fingerstick"
  | "other"
  | "unknown";

type GlucoseReading = {
  reading_id: number;
  glucose_mg_dl: number | string;
  measured_at: string;
  measurement_context?: MeasurementContext | null;
  measurement_method?: MeasurementMethod | null;
  input_method?: string | null;
  note?: string | null;
};

const contextLabels: Record<MeasurementContext, string> = {
  fasting: "공복",
  before_meal: "식전",
  after_meal: "식후",
  bedtime: "취침 전",
  other: "기타",
  unknown: "미분류",
};

const methodLabels: Record<MeasurementMethod, string> = {
  fingerstick: "손끝 채혈",
  other: "기타",
  unknown: "미분류",
};

// ==============================================
// 2. 날짜 처리
// ==============================================

// 현재 시각을 브라우저 로컬 시간으로 변환
function getLocalDateTime(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;

  return new Date(now.getTime() - offset)
    .toISOString()
    .slice(0, 16);
}

// 서버에서 받은 날짜를 datetime-local 형식으로 변환
function toLocalDateTime(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return getLocalDateTime();
  }

  const offset = date.getTimezoneOffset() * 60_000;

  return new Date(date.getTime() - offset)
    .toISOString()
    .slice(0, 16);
}

// 날짜 표시
function formatDateTime(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

// ==============================================
// 3. API 응답 처리
// ==============================================

async function getApiError(
  response: Response,
  fallback: string,
): Promise<string> {
  if (response.status === 401 || response.status === 403) {
    return "로그인 인증이 만료되었거나 접근 권한이 없습니다. 다시 로그인해 주세요.";
  }

  try {
    const body: unknown = await response.json();

    if (
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof body.detail === "string"
    ) {
      return body.detail;
    }
  } catch {
    // 오류 응답이 JSON이 아니라면 기본 메시지 사용
  }

  return `${fallback} (HTTP ${response.status})`;
}

// GET API 응답에서 혈당 기록 배열 추출
function parseReadings(data: unknown): GlucoseReading[] {
  let items: unknown = data;

  if (
    typeof data === "object" &&
    data !== null &&
    !Array.isArray(data)
  ) {
    const object = data as Record<string, unknown>;

    items =
      object.readings ??
      object.items ??
      object.data ??
      object.results;
  }

  if (!Array.isArray(items)) {
    throw new Error(
      "서버에서 예상하지 못한 혈당 기록 형식을 받았습니다.",
    );
  }

  for (const item of items) {
    if (
      typeof item !== "object" ||
      item === null ||
      !("reading_id" in item) ||
      !Number.isInteger(item.reading_id) ||
      !("glucose_mg_dl" in item) ||
      !Number.isFinite(Number(item.glucose_mg_dl)) ||
      !("measured_at" in item) ||
      typeof item.measured_at !== "string"
    ) {
      throw new Error(
        "혈당 기록에 올바르지 않은 데이터가 포함되어 있습니다.",
      );
    }
  }

  return items as GlucoseReading[];
}

// ==============================================
// 4. 혈당 관리 페이지
// ==============================================

export default function GlucosePage() {
  const { token, member } = useAuth();

  // 입력 폼
  const [glucose, setGlucose] = useState("");
  const [measuredAt, setMeasuredAt] = useState(getLocalDateTime);

  const [measurementContext, setMeasurementContext] =
    useState<MeasurementContext>("unknown");

  const [measurementMethod, setMeasurementMethod] =
    useState<MeasurementMethod>("fingerstick");

  const [note, setNote] = useState("");

  // DB에서 조회한 혈당 데이터
  const [readings, setReadings] = useState<GlucoseReading[]>([]);
  // 기록 목록의 기간 필터
  // 기본값은 오늘
  type RecordFilter = "today" | "3days" | "7days" | "all";

  const [recordFilter, setRecordFilter] =
    useState<RecordFilter>("today");

    // 현재 수정할 기록 ID
    const [editingId, setEditingId] = useState<number | null>(null);

    // 현재 삭제 중인 기록 ID
    const [deletingId, setDeletingId] = useState<number | null>(null);

    // 비동기 요청 상태
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    // 조회 오류와 저장·삭제 오류를 별도로 관리
    const [loadError, setLoadError] = useState("");
    const [formError, setFormError] = useState("");
    const [success, setSuccess] = useState("");

  // ============================================
  // 5. 혈당 기록 조회 (GET)
  // ============================================

  const loadReadings = useCallback(async (): Promise<boolean> => {
    if (!token) {
      setReadings([]);
      setLoadError("로그인 정보가 없습니다.");
      setLoading(false);
      return false;
    }

    setLoading(true);
    setLoadError("");

    try {
      // 조회 함수는 반드시 GET 요청만 보낸다.
      const response = await fetch("/api/glucose/readings", {
        method: "GET",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(
          await getApiError(
            response,
            "혈당 기록을 불러오지 못했습니다.",
          ),
        );
      }

      const data: unknown = await response.json();
      const parsed = parseReadings(data);

      // 측정 시각 기준 최신순
      parsed.sort(
        (a, b) =>
          new Date(b.measured_at).getTime() -
          new Date(a.measured_at).getTime(),
      );

      setReadings(parsed);
      return true;
    } catch (err) {
      setLoadError(
        err instanceof Error
          ? err.message
          : "혈당 기록 조회 중 오류가 발생했습니다.",
      );

      // 조회에 실패했다고 기존 기록을 삭제하지 않는다.
      return false;
    } finally {
      setLoading(false);
    }
  }, [token]);

  // 페이지가 처음 열릴 때 혈당 기록 조회
  useEffect(() => {
    void loadReadings();
  }, [loadReadings]);

  // ============================================
  // 6. 입력 폼 초기화
  // ============================================

  function resetForm() {
    setEditingId(null);
    setGlucose("");
    setMeasuredAt(getLocalDateTime());
    setMeasurementContext("unknown");
    setMeasurementMethod("fingerstick");
    setNote("");
  }

  // ============================================
  // 7. 기존 혈당 기록 수정 시작
  // ============================================

  function handleEdit(reading: GlucoseReading) {
    setEditingId(reading.reading_id);
    setGlucose(String(reading.glucose_mg_dl));
    setMeasuredAt(toLocalDateTime(reading.measured_at));

    setMeasurementContext(
      reading.measurement_context ?? "unknown",
    );

    setMeasurementMethod(
      reading.measurement_method ?? "unknown",
    );

    setNote(reading.note ?? "");

    setFormError("");
    setSuccess("");

    document.querySelector(".glucose-form")?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  }

  // 수정 취소
  function handleCancelEdit() {
    resetForm();
    setFormError("");
    setSuccess("");
  }

  // ============================================
  // 8. 혈당 등록(POST) / 수정(PUT)
  // ============================================

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!token || saving || deletingId !== null) {
      return;
    }

    setFormError("");
    setSuccess("");

    // 혈당값 검증
    const glucoseValue = Number(glucose);

    if (
      !glucose.trim() ||
      !Number.isFinite(glucoseValue) ||
      glucoseValue <= 0 ||
      glucoseValue > 1000 ||
      !/^\d+(\.\d)?$/.test(glucose.trim())
    ) {
      setFormError(
        "혈당은 0보다 크고 1000 이하인 수치로 입력해 주세요. 소수점은 한 자리까지 가능합니다.",
      );
      return;
    }

    // 측정 시각 검증
    const date = new Date(measuredAt);

    if (
      !measuredAt ||
      Number.isNaN(date.getTime()) ||
      date.getTime() > Date.now()
    ) {
      setFormError(
        "현재 또는 과거의 올바른 측정 시각을 입력해 주세요.",
      );
      return;
    }

    if (note.length > 500) {
      setFormError("메모는 500자 이내로 입력해 주세요.");
      return;
    }

    // 신규 등록인지 수정인지 판단
    const isEditing = editingId !== null;

    const url = isEditing
      ? `/api/glucose/readings/${editingId}`
      : "/api/glucose/readings";

    // 등록과 수정에 공통으로 필요한 정보
    const payload = {
      glucose_mg_dl: glucoseValue,
      measured_at: date.toISOString(),
      measurement_context: measurementContext,
      measurement_method: measurementMethod,
      note: note.trim() || null,
    };

    // input_method는 신규 등록(POST)에만 전달한다.
    // 수정(PUT)은 기존 input_method를 유지한다.
    const requestBody = isEditing
      ? payload
      : {
          ...payload,
          input_method: "manual",
        };

    setSaving(true);

    try {
      const response = await fetch(url, {
        method: isEditing ? "PUT" : "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        throw new Error(
          await getApiError(
            response,
            isEditing
              ? "혈당 기록 수정에 실패했습니다."
              : "혈당 기록 저장에 실패했습니다.",
          ),
        );
      }

      // 성공한 경우에만 입력 폼 초기화
      resetForm();

      // DB에서 최신 기록을 다시 가져온다.
      const refreshed = await loadReadings();

      if (refreshed) {
        setSuccess(
          isEditing
            ? "혈당 기록이 수정되었습니다."
            : "혈당 기록이 정상적으로 저장되었습니다.",
        );
      } else {
        setSuccess(
          isEditing
            ? "수정은 완료됐지만 목록을 다시 불러오지 못했습니다."
            : "저장은 완료됐지만 목록을 다시 불러오지 못했습니다.",
        );
      }
    } catch (err) {
      setFormError(
        err instanceof Error
          ? err.message
          : "혈당 기록 처리 중 오류가 발생했습니다.",
      );
    } finally {
      setSaving(false);
    }
  }

  // ============================================
  // 9. 혈당 기록 삭제 (DELETE)
  // ============================================

  async function handleDelete(readingId: number) {
    if (!token || saving || deletingId !== null) {
      return;
    }

    const confirmed = window.confirm(
      "이 혈당 기록을 삭제하시겠습니까?\n삭제한 기록은 복구할 수 없습니다.",
    );

    if (!confirmed) {
      return;
    }

    setDeletingId(readingId);
    setFormError("");
    setSuccess("");

    try {
      const response = await fetch(
        `/api/glucose/readings/${readingId}`,
        {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${token}`,
          },
        },
      );

      if (!response.ok) {
        throw new Error(
          await getApiError(
            response,
            "혈당 기록 삭제에 실패했습니다.",
          ),
        );
      }

      // 삭제한 기록만 현재 목록에서 제거한다.
      setReadings((previous) =>
        previous.filter(
          (item) => item.reading_id !== readingId,
        ),
      );

      // 현재 수정 중이던 기록을 삭제했다면 입력창 초기화
      if (editingId === readingId) {
        resetForm();
      }

      setSuccess("혈당 기록이 삭제되었습니다.");
    } catch (err) {
      setFormError(
        err instanceof Error
          ? err.message
          : "혈당 기록 삭제 중 오류가 발생했습니다.",
      );
    } finally {
      setDeletingId(null);
    }
  }

  // ============================================
  // 10. 조회된 혈당 기록 요약
  // ============================================

  
  // ============================================
  // 10. 혈당 요약
  // 최근 혈당: 전체 조회 기록 중 최신값
  // 평균 혈당: 최근 72시간 측정값 기준
  // ============================================

  const summary = useMemo(() => {
    const now = Date.now();
    const cutoff = now - 3 * 24 * 60 * 60 * 1000;

    // 전체 기록 중 가장 최근 측정값
    const sorted = readings
      .filter(
        (item) =>
          Number.isFinite(
            new Date(item.measured_at).getTime(),
          ) &&
          Number.isFinite(
            Number(item.glucose_mg_dl),
          ),
      )
      .sort(
        (a, b) =>
          new Date(b.measured_at).getTime() -
          new Date(a.measured_at).getTime(),
      );

    const latest =
      sorted.length > 0
        ? Number(sorted[0].glucose_mg_dl)
        : null;

    // 최근 3일(72시간) 측정 기록
    const recentValues = readings
      .filter((item) => {
        const time = new Date(
          item.measured_at,
        ).getTime();

        return (
          Number.isFinite(time) &&
          time >= cutoff &&
          time <= now
        );
      })
      .map((item) => Number(item.glucose_mg_dl))
      .filter((value) => Number.isFinite(value));

    if (recentValues.length === 0) {
      return {
        latest,
        average: null as number | null,
        count: 0,
      };
    }

    const total = recentValues.reduce(
      (sum, value) => sum + value,
      0,
    );

    return {
      latest,
      average:
        Math.round(
          (total / recentValues.length) * 10,
        ) / 10,
      count: recentValues.length,
    };
  }, [readings]);

  // ============================================
  // 기록 목록 기간별 필터
  // ============================================

  const filteredReadings = useMemo(() => {
    if (recordFilter === "all") {
      return readings;
    }

    const now = new Date();
    const nowTime = now.getTime();

    // 오늘 00:00:00 (브라우저 로컬 시간)
    const todayStart = new Date(
      now.getFullYear(),
      now.getMonth(),
      now.getDate(),
    ).getTime();

    const cutoff =
      recordFilter === "today"
        ? todayStart
        : nowTime -
          (recordFilter === "3days" ? 3 : 7) *
            24 *
            60 *
            60 *
            1000;

    return readings.filter((reading) => {
      const timestamp = new Date(
        reading.measured_at,
      ).getTime();

      return (
        Number.isFinite(timestamp) &&
        timestamp >= cutoff &&
        timestamp <= nowTime
      );
    });
  }, [readings, recordFilter]);

  const recordFilterLabel: Record<RecordFilter, string> = {
    today: "오늘",
    "3days": "최근 3일",
    "7days": "최근 7일",
    all: "전체",
  };
  // ============================================
  // 11. 화면 렌더링
  // ============================================

  return (
    <main className="glucose-page">
      {/* 상단 제목 */}
      <div className="glucose-page-header">
        <Link to="/home" className="glucose-back-link">
          <ArrowLeft size={18} />
          홈으로 돌아가기
        </Link>

        <div className="glucose-title-row">
          <div>
            <p className="glucose-eyebrow">
              FITIF HEALTH TRACKER
            </p>

            <h1>나의 혈당 관리</h1>

            <p className="glucose-subtitle">
              {member?.name?.trim() ||
                member?.login_id ||
                "회원"}
              님의 혈당을 직접 기록하고 확인하세요.
            </p>
          </div>

          <div className="glucose-title-icon">
            <Droplets size={28} />
          </div>
        </div>
      </div>

      {/* 혈당 요약 */}
      <section className="glucose-summary-grid">
        <div className="glucose-summary-card">
          <span className="glucose-summary-label">
            <Droplets size={17} />
            최근 혈당
          </span>

          <div className="glucose-summary-value">
            {summary.latest === null
              ? "—"
              : summary.latest}
            <span>mg/dL</span>
          </div>

          <p>조회된 기록 중 가장 최근 측정값</p>
        </div>

        <div className="glucose-summary-card">
          <span className="glucose-summary-label">
            <ChartNoAxesColumn size={17} />
            최근 3일 평균 혈당
          </span>

          <div className="glucose-summary-value">
            {summary.average === null
              ? "—"
              : summary.average}
            <span>mg/dL</span>
          </div>

          <p>
            최근 3일 측정 기록 {summary.count}건 기준
          </p>
        </div>
      </section>

      {/* 혈당 시계열 그래프 */}
      <GlucoseTrendChart readings={readings} />

      {/* ======================================
          혈당 입력 / 수정 영역
          ====================================== */}

      <section className="glucose-panel">
        <div className="glucose-panel-heading">
          {editingId !== null ? (
            <Pencil size={20} />
          ) : (
            <Plus size={20} />
          )}

          <h2>
            {editingId !== null
              ? "혈당 기록 수정"
              : "새 혈당 기록"}
          </h2>
        </div>

        <form
          onSubmit={handleSave}
          className="glucose-form"
        >
          {/* 혈당 수치 */}
          <div className="glucose-field">
            <label htmlFor="glucose-value">
              혈당 수치{" "}
              <span className="glucose-required">*</span>
            </label>

            <div className="glucose-number-wrap">
              <input
                id="glucose-value"
                type="number"
                min="0.1"
                max="1000"
                step="0.1"
                value={glucose}
                onChange={(event) =>
                  setGlucose(event.target.value)
                }
                placeholder="예: 110"
                required
              />
              <span>mg/dL</span>
            </div>
          </div>

          {/* 측정 시각 */}
          <div className="glucose-field">
            <label htmlFor="glucose-datetime">
              측정 시각{" "}
              <span className="glucose-required">*</span>
            </label>

            <input
              id="glucose-datetime"
              type="datetime-local"
              value={measuredAt}
              max={getLocalDateTime()}
              onChange={(event) =>
                setMeasuredAt(event.target.value)
              }
              required
            />
          </div>

          {/* 측정 상황 / 방법 */}
          <div className="glucose-field-grid">
            <div className="glucose-field">
              <label htmlFor="glucose-context">
                측정 상황
              </label>

              <select
                id="glucose-context"
                value={measurementContext}
                onChange={(event) =>
                  setMeasurementContext(
                    event.target.value as MeasurementContext,
                  )
                }
              >
                <option value="unknown">선택 안 함</option>
                <option value="fasting">공복</option>
                <option value="before_meal">식전</option>
                <option value="after_meal">식후</option>
                <option value="bedtime">취침 전</option>
                <option value="other">기타</option>
              </select>
            </div>

            <div className="glucose-field">
              <label htmlFor="glucose-method">
                측정 방법
              </label>

              <select
                id="glucose-method"
                value={measurementMethod}
                onChange={(event) =>
                  setMeasurementMethod(
                    event.target.value as MeasurementMethod,
                  )
                }
              >
                <option value="fingerstick">
                  손끝 채혈
                </option>
                <option value="other">기타</option>
                <option value="unknown">선택 안 함</option>
              </select>
            </div>
          </div>

          {/* 메모 */}
          <div className="glucose-field">
            <label htmlFor="glucose-note">
              메모 (선택)
            </label>

            <textarea
              id="glucose-note"
              value={note}
              onChange={(event) =>
                setNote(event.target.value)
              }
              maxLength={500}
              rows={3}
              placeholder="식사나 운동 등 기록하고 싶은 내용을 입력하세요."
            />

            <span className="glucose-character-count">
              {note.length}/500자
            </span>
          </div>

          {/* 저장 / 수정 / 삭제 오류 */}
          {formError && (
            <p
              className="glucose-alert glucose-alert-error"
              role="alert"
            >
              {formError}
            </p>
          )}

          {/* 작업 성공 메시지 */}
          {success && (
            <p
              className="glucose-alert glucose-alert-success"
              role="status"
            >
              {success}
            </p>
          )}

          {/* 저장 / 수정 버튼 */}
          <button
            type="submit"
            className="glucose-save-button"
            disabled={
              saving ||
              deletingId !== null ||
              !token
            }
          >
            {editingId !== null ? (
              <Pencil size={18} />
            ) : (
              <Plus size={18} />
            )}

            {saving
              ? "처리 중..."
              : editingId !== null
                ? "혈당 기록 수정"
                : "혈당 기록 저장"}
          </button>

          {/* 수정 취소 */}
          {editingId !== null && (
            <button
              type="button"
              className="glucose-cancel-button"
              onClick={handleCancelEdit}
              disabled={saving}
            >
              수정 취소
            </button>
          )}
        </form>
      </section>

      {/* ======================================
          혈당 기록 목록
          ====================================== */}

      <section className="glucose-panel">
      <div className="glucose-list-heading">
        <div className="glucose-panel-heading">
          <Clock3 size={20} />
          <h2>혈당 기록 내역</h2>
        </div>

        <button
          type="button"
          className="glucose-refresh-button"
          onClick={() => void loadReadings()}
          disabled={loading || saving || deletingId !== null}
        >
          <RefreshCw size={16} />
          새로고침
        </button>
      </div>

      {/* 기간 선택 버튼은 제목 영역 바깥에 배치 */}
      <div
        className="glucose-record-filters"
        role="group"
        aria-label="혈당 기록 조회 기간"
      >
        {(
          [
            ["today", "오늘"],
            ["3days", "3일"],
            ["7days", "7일"],
            ["all", "전체"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={
              recordFilter === value
                ? "glucose-record-filter active"
                : "glucose-record-filter"
            }
            aria-pressed={recordFilter === value}
            onClick={() => setRecordFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>

      <p className="glucose-record-filter-count">
        {recordFilterLabel[recordFilter]} 측정 기록{" "}
        <strong>{filteredReadings.length}건</strong>
      </p>


        {/* 조회 실패 안내 */}
        {loadError && (
          <p
            className="glucose-alert glucose-alert-error"
            role="alert"
            style={{ marginTop: 16 }}
          >
            {loadError}
          </p>
        )}

        {/* 조회 상태에 따른 화면 */}
        {loading ? (
          <div className="glucose-empty-state">
            혈당 기록을 불러오는 중입니다.
          </div>
        ) : loadError && readings.length === 0 ? (
          <div className="glucose-empty-state">
            <strong>
            선택한 기간에 혈당 기록이 없습니다.
            </strong>
            <p>
              다른 기간을 선택하거나 새 기록을 등록해 주세요.
            </p>
            </div>
        ) : filteredReadings.length === 0 ? (
          <div className="glucose-empty-state">
            <Droplets size={32} />
            <strong>
              아직 등록된 혈당 기록이 없어요.
            </strong>
            <p>
              위 입력창에서 첫 번째 혈당을 기록해 보세요.
            </p>
          </div>
        ) : (
          <div className="glucose-record-list">
            {filteredReadings.map((reading) => (
              <article
                key={reading.reading_id}
                className="glucose-record-item"
              >
                <div className="glucose-record-info">
                  {/* 측정 상황 */}
                  <span className="glucose-record-context">
                    {contextLabels[
                      reading.measurement_context ??
                        "unknown"
                    ] ?? "미분류"}
                  </span>

                  {/* 혈당값 */}
                  <strong>
                    {Number(reading.glucose_mg_dl)}
                    <small> mg/dL</small>
                  </strong>

                  {/* 측정 시각 / 방법 */}
                  <span className="glucose-record-date">
                    {formatDateTime(reading.measured_at)}
                    {" · "}
                    {methodLabels[
                      reading.measurement_method ??
                        "unknown"
                    ] ?? "기타"}
                  </span>

                  {/* 메모 */}
                  {reading.note && (
                    <p className="glucose-record-note">
                      {reading.note}
                    </p>
                  )}
                </div>

                {/* 수정 / 삭제 버튼 */}
                <div className="glucose-record-actions">
                  <button
                    type="button"
                    className="glucose-edit-button"
                    onClick={() =>
                      handleEdit(reading)
                    }
                    disabled={
                      saving ||
                      deletingId !== null
                    }
                  >
                    <Pencil size={15} />
                    수정
                  </button>

                  <button
                    type="button"
                    className="glucose-delete-button"
                    onClick={() =>
                      void handleDelete(reading.reading_id)
                    }
                    disabled={
                      saving ||
                      deletingId !== null
                    }
                  >
                    <Trash2 size={15} />

                    {deletingId === reading.reading_id
                      ? "삭제 중"
                      : "삭제"}
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      {/* 의료정보 안내 */}
      <p className="glucose-disclaimer">
        FITIF에 기록한 혈당 데이터는 건강 관리
        참고용이며, 의료 전문가의 진단이나 치료를
        대신하지 않습니다.
      </p>
    </main>
  );
}
