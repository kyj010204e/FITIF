import {
  ArrowLeft,
  ChevronRight,
  Droplets,
  FilePlus2,
  Watch,
} from "lucide-react";
import { Link } from "react-router";
import "./HealthRecordsPage.css";

export const HEALTH_RECORDS_PATH = "/records";

const recordMenus = [
  {
    path: `${HEALTH_RECORDS_PATH}/glucose`,
    title: "혈당 관리",
    description: "혈당을 기록하고 추이를 확인해요",
    icon: Droplets,
  },
  {
    path: `${HEALTH_RECORDS_PATH}/documents`,
    title: "의료문서 등록",
    description: "처방전이나 검진 결과를 등록해요",
    icon: FilePlus2,
  },
  {
    path: `${HEALTH_RECORDS_PATH}/wearables`,
    title: "웨어러블 등록",
    description: "웨어러블 기기를 연결해요",
    icon: Watch,
  },
];

export default function HealthRecordsPage() {
  return (
    <section className="health-records" aria-labelledby="health-records-title">
      <h1 id="health-records-title">건강기록</h1>
      <ul className="health-records__list">
        {recordMenus.map(({ path, title, description, icon: Icon }) => (
          <li key={path}>
            <Link to={path} className="health-records__card">
              <span className="health-records__icon" aria-hidden="true">
                <Icon size={24} />
              </span>
              <span className="health-records__label">
                <strong>{title}</strong>
                <span>{description}</span>
              </span>
              <ChevronRight size={20} aria-hidden="true" />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function PendingRecordPage({ title, message }: { title: string; message: string }) {
  return (
    <section className="health-records">
      <Link to={HEALTH_RECORDS_PATH} className="health-records__back">
        <ArrowLeft size={18} aria-hidden="true" />
        건강기록
      </Link>
      <h1>{title}</h1>
      <p>{message}</p>
    </section>
  );
}

export function MedicalDocumentPage() {
  return (
    <PendingRecordPage
      title="의료문서 등록"
      message="의료문서 업로드와 OCR 연결을 준비 중이에요."
    />
  );
}

export function WearableRegistrationPage() {
  return (
    <PendingRecordPage
      title="웨어러블 등록"
      message="웨어러블 기기 연결을 준비 중이에요."
    />
  );
}
