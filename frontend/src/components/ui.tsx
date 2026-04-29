import React from 'react';
import type { Status } from '../lib/types';

export function Button({ variant = 'primary', busy, children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'danger' | 'ghost'; busy?: boolean }) {
  return <button className={`btn btn-${variant}`} disabled={busy || props.disabled} {...props}>{busy ? '...' : children}</button>;
}

export function Card({ title, action, children }: { title?: React.ReactNode; action?: React.ReactNode; children: React.ReactNode }) {
  return <section className="card">{(title || action) && <div className="card-head"><h2>{title}</h2><div>{action}</div></div>}{children}</section>;
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className="input" {...props} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className="input" {...props} />;
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className="input textarea" {...props} />;
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

export function Badge({ value }: { value?: Status | string | null }) {
  const v = value || 'unknown';
  return <span className={`badge badge-${String(v).toLowerCase()}`}>{v}</span>;
}

export function Empty({ children = 'Nothing here yet.' }: { children?: React.ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function ErrorBox({ error }: { error?: string | null }) {
  if (!error) return null;
  return <div className="error-box">{error}</div>;
}

export function Spinner() { return <div className="spinner" />; }

export function CopyButton({ value, label = 'Copy' }: { value: string; label?: string }) {
  const [copied, setCopied] = React.useState(false);
  return <Button variant="secondary" onClick={async () => { await navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1200); }}>{copied ? 'Copied' : label}</Button>;
}
