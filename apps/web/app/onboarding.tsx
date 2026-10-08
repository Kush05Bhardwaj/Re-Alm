"use client";

import { useEffect, useState, type FormEvent } from "react";
import type { APIResponse, EnvironmentType, Player, Quest } from "@realm/types";

type Screen = "boot" | "welcome" | "create" | "world";
type Archetype = "explorer" | "observer" | "seeker" | "wanderer";
const archetypes: { id: Archetype; title: string; description: string; mark: string }[] = [
  { id: "explorer", title: "Explorer", description: "Longer journeys into the unknown.", mark: "⌖" },
  { id: "observer", title: "Observer", description: "Notice what the world leaves in plain sight.", mark: "◉" },
  { id: "seeker", title: "Seeker", description: "Follow mysteries, fragments, and clues.", mark: "⌕" },
  { id: "wanderer", title: "Wanderer", description: "Make room for strange, unexpected paths.", mark: "↗" },
];
const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1").replace(/\/api\/v1\/?$/, "");
const playerKey = "realm.player-id";

async function requestPlayer(path: string, init?: RequestInit, id?: string): Promise<Player> {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(id ? { "X-Player-ID": id } : {}), ...init?.headers },
  });
  const body = (await response.json()) as APIResponse<Player>;
  if (!response.ok || !body.data) throw new Error(body.error?.message ?? "The system could not complete that request.");
  return body.data;
}

export default function Onboarding() {
  const [screen, setScreen] = useState<Screen>("boot");
  const [bootStage, setBootStage] = useState(0);
  const [name, setName] = useState("");
  const [archetype, setArchetype] = useState<Archetype>("explorer");
  const [interests, setInterests] = useState("");
  const [duration, setDuration] = useState(30);
  const [player, setPlayer] = useState<Player | null>(null);
  const [quest, setQuest] = useState<Quest | null>(null);
  const [environment, setEnvironment] = useState<EnvironmentType>("unknown");
  const [questLoading, setQuestLoading] = useState(false);
  const [questError, setQuestError] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const first = window.setTimeout(() => setBootStage(1), 650);
    const second = window.setTimeout(async () => {
      setBootStage(2);
      const id = window.localStorage.getItem(playerKey);
      if (id) {
        try {
          const currentPlayer = await requestPlayer("/api/player/me", undefined, id);
          setPlayer(currentPlayer);
          try {
            const currentResponse = await fetch(`${apiBase}/api/quest/current`, { headers: { "X-Player-ID": id } });
            const currentBody = (await currentResponse.json()) as APIResponse<Quest>;
            if (currentResponse.ok && currentBody.data) setQuest(currentBody.data);
          } catch { /* The profile remains available if quest history cannot load. */ }
          setScreen("world");
          return;
        } catch {
          window.localStorage.removeItem(playerKey);
        }
      }
      setScreen("welcome");
    }, 2100);
    return () => { window.clearTimeout(first); window.clearTimeout(second); };
  }, []);

  async function createPlayer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const created = await requestPlayer("/api/player/create", {
        method: "POST",
        body: JSON.stringify({ display_name: name.trim(), archetype, preferences: { interests: interests.trim(), quest_duration_minutes: duration } }),
      });
      window.localStorage.setItem(playerKey, created.id);
      setPlayer(created);
      setScreen("world");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Connection to the system failed.");
    } finally {
      setSubmitting(false);
    }
  }

  async function requestQuest() {
    if (!player || questLoading) return;
    setQuestLoading(true);
    setQuestError("");
    try {
      const response = await fetch(`${apiBase}/api/quest/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Player-ID": player.id },
        body: JSON.stringify({ environment: { setting: environment } }),
      });
      const body = (await response.json()) as APIResponse<Quest>;
      if (!response.ok || !body.data) throw new Error(body.error?.message ?? "The Game Master could not create a quest.");
      setQuest(body.data);
    } catch (cause) {
      setQuestError(cause instanceof Error ? cause.message : "The Game Master is unreachable.");
    } finally {
      setQuestLoading(false);
    }
  }

  return <main className="realm-shell" id="top">
    <div className="ambient ambient-one" /><div className="ambient ambient-two" />
    <header className="topbar"><a className="wordmark" href="#top">RE<span>:</span>ALM</a><span className="topbar-status"><i /> SYSTEM {screen === "world" ? "ONLINE" : "STANDBY"}</span></header>

    {screen === "boot" && <section className="boot-screen" aria-live="polite">
      <div className="boot-glyph"><span>R</span></div><p className="eyebrow">REALM ENGINE // INITIAL SEQUENCE</p><h1>RE:ALM SYSTEM</h1>
      <div className="boot-copy"><p className="visible">INITIALIZING...</p><p className={bootStage >= 1 ? "visible" : "dimmed"}>WORLD CONNECTION <span>100%</span></p><p className={bootStage >= 2 ? "visible detected" : "dimmed"}>PLAYER DETECTED <b>◆</b></p></div>
      <div className="boot-track"><span style={{ width: `${bootStage === 0 ? 24 : bootStage === 1 ? 68 : 100}%` }} /></div><div className="boot-footer"><span>ESTABLISHING LINK</span><span>SYS 01.00</span></div>
    </section>}

    {screen === "welcome" && <section className="welcome-screen view-enter">
      <div className="signal-line"><span /> AN UNKNOWN WORLD AWAITS</div><h1>WELCOME,<br /><em>PLAYER.</em></h1>
      <p className="welcome-copy">Your world is unexplored.<br />There is more waiting beyond the familiar.</p>
      <button className="primary-button" onClick={() => setScreen("create")}><span>BEGIN YOUR FIRST QUEST</span><b>↗</b></button>
      <p className="micro-copy">FIRST, LET THE SYSTEM KNOW YOU.</p><div className="welcome-coordinate">LAT 00° 00&apos; 00&quot; <span>—</span> WORLD LINK STABLE</div>
    </section>}

    {screen === "create" && <section className="creation-screen view-enter">
      <div className="section-kicker"><span>01</span> PLAYER REGISTRATION</div>
      <div className="creation-heading"><h1>Who are you,<br /><em>traveler?</em></h1><p>Your first steps shape the kind of paths the system will reveal.</p></div>
      <form onSubmit={createPlayer}>
        <label className="field-label" htmlFor="player-name">NAME <span>REQUIRED</span></label>
        <input id="player-name" className="name-input" autoFocus maxLength={32} placeholder="Enter your name" value={name} onChange={(event) => setName(event.target.value)} required />
        <div className="field-label archetype-label">CHOOSE YOUR ARCHETYPE <span>THIS CAN CHANGE LATER</span></div>
        <div className="archetype-grid" role="radiogroup" aria-label="Choose your archetype">{archetypes.map((item) => <button className={`archetype-card ${archetype === item.id ? "selected" : ""}`} type="button" role="radio" aria-checked={archetype === item.id} onClick={() => setArchetype(item.id)} key={item.id}><span className="archetype-mark">{item.mark}</span><strong>{item.title}</strong><span className="archetype-description">{item.description}</span><span className="radio-dot" /></button>)}</div>
        <div className="form-bottom-grid"><div><label className="field-label" htmlFor="interests">PERSONAL PREFERENCES <span>OPTIONAL</span></label><input id="interests" className="text-input" maxLength={500} placeholder="What are you drawn to?" value={interests} onChange={(event) => setInterests(event.target.value)} /></div><div><label className="field-label" htmlFor="duration">TIME FOR A QUEST <span>PER SESSION</span></label><select id="duration" className="text-input" value={duration} onChange={(event) => setDuration(Number(event.target.value))}><option value={15}>A few moments · 15 min</option><option value={30}>A little while · 30 min</option><option value={60}>An open hour · 60 min</option><option value={120}>No rush · 2 hours</option></select></div></div>
        {error && <p className="form-error" role="alert">SYSTEM ERROR — {error}</p>}
        <div className="form-actions"><p>YOUR STORY STARTS AT LEVEL 01.</p><button className="primary-button" type="submit" disabled={submitting || !name.trim()}><span>{submitting ? "CREATING PLAYER..." : "ENTER THE WORLD"}</span><b>↗</b></button></div>
      </form>
    </section>}

    {screen === "world" && player && <section className="world-screen view-enter">
      <div className="world-welcome"><div className="signal-line"><span /> WORLD LINK ESTABLISHED</div><p className="world-overline">YOUR STORY BEGINS HERE</p><h1>Welcome to the<br /><em>unexplored, {player.display_name}.</em></h1><p className="world-description">The world is waiting. Keep your eyes open; every path has a first step.</p>
        <section className="quest-panel" aria-live="polite">
          <div className="quest-kicker">NEXT QUEST <span>// GAME MASTER</span></div>
          {!quest && <p className="quest-intro">The Game Master is listening to your path and ready to shape what comes next.</p>}
          <label className="field-label quest-setting-label" htmlFor="quest-setting">YOUR SURROUNDINGS</label>
          <select id="quest-setting" className="text-input quest-setting" value={environment} onChange={(event) => setEnvironment(event.target.value as EnvironmentType)}>
            <option value="unknown">Let the world surprise me</option><option value="home">At home</option><option value="indoor">An indoor public place</option><option value="urban">Around the city</option><option value="nature">Outdoors in nature</option>
          </select>
          <button className="primary-button quest-button" onClick={requestQuest} disabled={questLoading}><span>{questLoading ? "CONSULTING THE GAME MASTER..." : quest ? "GENERATE ANOTHER QUEST" : "GENERATE MY FIRST QUEST"}</span><b>↗</b></button>
          {questError && <p className="form-error" role="alert">SYSTEM ERROR — {questError}</p>}
          {quest && <article className="quest-result">
            <div className="quest-result-meta"><span>{quest.category.toUpperCase()}</span><span>LV. {String(quest.level).padStart(2, "0")} · {quest.estimated_minutes} MIN</span></div>
            <h2>{quest.title}</h2><p>{quest.description}</p>
            <ol>{quest.objectives.map((objective) => <li key={objective.id}>{objective.description}</li>)}</ol>
            <div className="quest-rewards"><span>✦ {quest.aether_reward} AETHER</span><span>{quest.xp_reward} EXP</span><span>DIFFICULTY {quest.difficulty}/5</span></div>
          </article>}
        </section>
      </div>
      <aside className="player-card"><div className="card-topline"><span>PLAYER PROFILE</span><span className="online-tag"><i /> ACTIVE</span></div>
        <div className="profile-identity"><div className="avatar-seal">{player.display_name.slice(0, 1).toUpperCase()}</div><div><p className="player-label">PLAYER</p><h2>{player.display_name}</h2></div><span className="level-badge">LV. {String(player.level).padStart(2, "0")}</span></div>
        <div className="experience-block"><div className="exp-label"><span>EXP</span><span>{player.experience} <i>/</i> {player.experience_to_next_level}</span></div><div className="exp-track"><span style={{ width: `${Math.min(100, (player.experience / player.experience_to_next_level) * 100)}%` }} /></div></div>
        <div className="profile-meta"><div><span className="meta-label">AETHER</span><strong className="aether-value"><i>✦</i> {player.aether}</strong></div><div><span className="meta-label">CLASS</span><strong>{player.archetype.charAt(0).toUpperCase() + player.archetype.slice(1)}</strong></div></div>
        <div className="stats-block"><div className="stats-title">BASE ATTRIBUTES <span>01</span></div><div className="stats-grid">{([["STR", player.stats.str], ["AGI", player.stats.agi], ["INT", player.stats.int], ["VIT", player.stats.vit], ["LCK", player.stats.lck]] as const).map(([label, value]) => <div className="stat" key={label}><span>{label}</span><b>{String(value).padStart(2, "0")}</b></div>)}</div></div>
        <div className="profile-footer">PATH: {player.preferences.quest_duration_minutes} MIN <span>IDENTITY SAVED</span></div>
      </aside><div className="world-coordinate">RE:ALM <span>·</span> UNKNOWN REGION <span>·</span> DISCOVERY AWAITS</div>
    </section>}
    <footer className="site-footer"><span>RE:ALM <i>—</i> FIND YOUR WAY THROUGH.</span><span>AN OPEN WORLD, ONE STEP AT A TIME.</span></footer>
  </main>;
}
