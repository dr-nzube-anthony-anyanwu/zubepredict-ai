import Link from "next/link";
import { signIn, signUp } from "./actions";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; message?: string }>;
}) {
  const notice = await searchParams;
  return (
    <main className="auth-shell">
      <section className="auth-story">
        <Link className="brand" href="/"><span className="brand-mark">ZP</span><span>ZubePredict AI</span></Link>
        <div>
          <p className="eyebrow">EVIDENCE-FIRST MODEL DEVELOPMENT</p>
          <h1>One workspace.<br />Every experiment.</h1>
          <p>Continue the same project from the dashboard or your securely linked Telegram account.</p>
        </div>
        <small>Decision support and research use unless independently validated.</small>
      </section>
      <section className="auth-panel">
        <div className="auth-card">
          <p className="kicker">WELCOME</p>
          <h2>Sign in to your workspace</h2>
          <p className="muted">Use the account you created with ZubePredict.</p>
          {notice.error && <p className="notice error" role="alert">{notice.error}</p>}
          {notice.message && <p className="notice success">{notice.message}</p>}
          <form className="form-stack">
            <label>Email address<input name="email" type="email" autoComplete="email" required /></label>
            <label>Password<input name="password" type="password" autoComplete="current-password" minLength={8} required /></label>
            <button className="button primary" formAction={signIn}>Sign in</button>
            <button className="button secondary" formAction={signUp}>Create account</button>
          </form>
          <p className="fine-print">Your session is managed by Supabase Auth. ZubePredict never sends backend secrets to this browser.</p>
        </div>
      </section>
    </main>
  );
}
