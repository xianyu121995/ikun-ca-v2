"use client";

import type { Key, ReactNode } from "react";
import { cx } from "./primitives.js";
import { Icon } from "./icons.js";

export interface TableColumn<Row> { key: string; header: string; render: (row: Row) => ReactNode; align?: "left" | "right"; width?: string; sortable?: boolean }
export interface TableSort { key: string; direction: "asc" | "desc" }
export interface DataTableProps<Row> {
  caption: string; columns: readonly TableColumn<Row>[]; rows: readonly Row[]; rowKey: (row: Row) => Key;
  sort?: TableSort; onSortChange?: (sort: TableSort) => void; loading?: boolean; refreshing?: boolean;
  empty?: ReactNode; error?: ReactNode; minWidth?: number;
}
export function DataTable<Row>({ caption, columns, rows, rowKey, sort, onSortChange, loading = false, refreshing = false, empty, error, minWidth = 760 }: DataTableProps<Row>) {
  const ariaBusy = loading || refreshing;
  return <div className="ik-table-block" aria-busy={ariaBusy}>
    {refreshing && <p className="ik-table-updating" role="status"><span className="ik-spinner" aria-hidden="true" /> 更新中，当前数据仍可查看</p>}
    {error && <div className="ik-table-notice">{error}</div>}
    {loading && <span className="ik-sr-only" role="status">正在加载{caption}</span>}
    <div className="ik-table-scroll" tabIndex={0} role="region" aria-label={`${caption}，可横向滚动`}>
      <table className="ik-table" style={{ minWidth }}><caption className="ik-sr-only">{caption}</caption><thead><tr>{columns.map(column => {
        const active = sort?.key === column.key;
        const sortable = column.sortable && onSortChange;
        return <th key={column.key} scope="col" style={{ width: column.width }} className={cx(column.align === "right" && "ik-align-right")} aria-sort={sortable ? (active ? (sort.direction === "asc" ? "ascending" : "descending") : "none") : undefined}>
          {sortable ? <button type="button" className="ik-sort-button" onClick={() => onSortChange({ key: column.key, direction: active && sort.direction === "asc" ? "desc" : "asc" })}>{column.header}<Icon name="sort" className={cx(active && "is-active")} /></button> : column.header}
        </th>;
      })}</tr></thead><tbody>{loading && !rows.length ? Array.from({ length: 5 }, (_, i) => <tr key={i} aria-hidden="true">{columns.map(c => <td key={c.key}><span className="ik-skeleton" /></td>)}</tr>) : rows.map(row => <tr key={rowKey(row)}>{columns.map(c => <td key={c.key} className={cx(c.align === "right" && "ik-align-right")}>{c.render(row)}</td>)}</tr>)}</tbody></table>
    </div>
    {!loading && !rows.length && !error && <div className="ik-table-empty">{empty ?? <p>暂无数据</p>}</div>}
  </div>;
}
