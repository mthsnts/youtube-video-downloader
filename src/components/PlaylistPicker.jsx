function formatDuration(sec) {
  if (sec == null) return "";
  sec = Math.round(sec);
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return (h ? `${h}:${String(m).padStart(2, "0")}` : m) + ":" + String(s).padStart(2, "0");
}

/** Playlist videos as cards with thumbnail, title and duration; click a card to (un)select it. */
export default function PlaylistPicker({ playlist, selected, onChange }) {
  const available = playlist.videos.filter((v) => v.available).map((v) => v.id);

  function toggle(id, on) {
    const next = new Set(selected);
    if (on) next.add(id);
    else next.delete(id);
    onChange(next);
  }

  return (
    <div className="playlist">
      <div className="pl-head">
        <strong>{playlist.title}</strong>
        <span className="pl-count">
          {selected.size} de {playlist.videos.length} selecionados
        </span>
        <button type="button" className="link" onClick={() => onChange(new Set(available))}>
          Selecionar todos
        </button>
        <button type="button" className="link" onClick={() => onChange(new Set())}>
          Nenhum
        </button>
      </div>
      <div className="cards">
        {playlist.videos.map((video) => {
          const on = selected.has(video.id);
          return (
            <label
              key={video.id}
              className={`card${on ? " selected" : ""}${video.available ? "" : " disabled"}`}
            >
              <img src={video.thumbnail} alt="" loading="lazy" />
              <input
                type="checkbox"
                checked={on}
                disabled={!video.available}
                onChange={(e) => toggle(video.id, e.target.checked)}
              />
              {video.duration ? <span className="dur">{formatDuration(video.duration)}</span> : null}
              <div className="title" title={video.title}>
                {video.title}
              </div>
            </label>
          );
        })}
      </div>
    </div>
  );
}
