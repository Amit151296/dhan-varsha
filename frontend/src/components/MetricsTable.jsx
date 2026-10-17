export default function MetricsTable({ job }) {
  if (!job.rows.length) {
    return <p className="analyser-empty">No stocks matched this sector.</p>;
  }

  const columns = Object.keys(job.rows[0].metrics);

  return (
    <div className="metrics-table-wrapper">
      <table className="metrics-table">
        <thead>
          <tr>
            <th className="metrics-table-sticky-col">Name</th>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {job.rows.map((row) => (
            <tr key={row.name}>
              <td className="metrics-table-sticky-col">{row.name}</td>
              {columns.map((column) => {
                const highlight = row.highlights[column];
                const style = highlight
                  ? { backgroundColor: highlight.background, color: highlight.color }
                  : undefined;
                return (
                  <td key={column} style={style}>
                    {row.metrics[column]}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
