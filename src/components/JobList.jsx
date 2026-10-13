import { fileUrl } from "../api.js";

const STATUS = { queued: "Na fila", running: "Baixando...", done: "Pronto", error: "Erro" };

function Job({ job }) {
  const percent = job.percent ?? 0;
  const many = job.files.length > 1;
  const detail =
    job.status === "error" ? job.error
    : job.status === "done" ? ""
    : job.current + (job.percent == null ? "" : ` (${percent}%)`);

  return (
    <div className="job">
      <strong>{STATUS[job.status]}</strong> · {job.format.toUpperCase()}
      <div className="url">{job.label || job.url}</div>
      {detail ? <div>{detail}</div> : null}
      {job.status === "running" ? (
        <div className="bar">
          <div style={{ width: `${percent}%` }} />
        </div>
      ) : null}
      {job.status === "done" ? (
        <>
          <div className="files">
            {job.files.map((name, i) => (
              <a
                key={name}
                className={`save${many ? " secondary" : ""}`}
                href={fileUrl(job.id, `/files/${i}`)}
                download
                title={name}
              >
                Salvar {name}
              </a>
            ))}
            {many ? (
              <a className="save" href={fileUrl(job.id, "/zip")} download>
                Salvar todos (.zip)
              </a>
            ) : null}
          </div>
          {job.error ? <div className="warn">Alguns vídeos falharam: {job.error}</div> : null}
        </>
      ) : null}
    </div>
  );
}

export default function JobList({ jobs, offline }) {
  if (offline) return <div className="job error">Sem conexão com o servidor: {offline}</div>;
  return jobs.map((job) => <Job key={job.id} job={job} />);
}
