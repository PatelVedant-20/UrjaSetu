import { useState, type ChangeEvent, type FormEvent } from "react";
import { Camera, Sun, Zap, ArrowRight, ShieldCheck } from "lucide-react";
import { Avatar, Card, Heading, MetricCards, PeriodTabs, fmt } from "./ui";
import { HistoryChart } from "./charts";
import type { Experience, Perform, Period, Setup } from "./types";

export const defaultSetup: Setup = {
  city: "Ahmedabad",
  home_type: "independent",
  occupants: 4,
  monthly_kwh: 360,
  ac_count: 1,
  has_ev: false,
  daytime_home: true,
  orientation: "south",
  tilt: 23,
  retail_rate: 7,
  share_stats: true,
  avatar: null,
  photo: null,
};

export function PhotoInput({
  label,
  value,
  onChange,
  large = false,
}: {
  label: string;
  value: string | null;
  onChange: (value: string | null) => void;
  large?: boolean;
}) {
  const [error, setError] = useState("");
  async function choose(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError("");
    if (
      !["image/png", "image/jpeg", "image/webp"].includes(file.type) ||
      file.size > 10 * 1024 * 1024
    ) {
      setError("Choose a PNG, JPEG or WebP smaller than 10 MB.");
      return;
    }
    const url = URL.createObjectURL(file);
    try {
      const image = new Image();
      image.src = url;
      await image.decode();
      const canvas = document.createElement("canvas");
      const scale = Math.min(
        1,
        (large ? 960 : 256) / Math.max(image.width, image.height),
      );
      canvas.width = Math.round(image.width * scale);
      canvas.height = Math.round(image.height * scale);
      canvas
        .getContext("2d")!
        .drawImage(image, 0, 0, canvas.width, canvas.height);
      let encoded = canvas.toDataURL("image/jpeg", 0.78);
      if (encoded.length > (large ? 300000 : 200000))
        encoded = canvas.toDataURL("image/jpeg", 0.45);
      if (encoded.length > (large ? 300000 : 200000))
        throw new Error("Choose a smaller photo.");
      onChange(encoded);
    } catch {
      setError("That image could not be processed. Try a smaller photo.");
    } finally {
      URL.revokeObjectURL(url);
      event.target.value = "";
    }
  }
  return (
    <div className="ux-photo-input">
      {value && (
        <img
          src={value}
          alt={label}
          className={large ? "house-photo" : "profile-photo"}
        />
      )}
      <label className="ux-file">
        <Camera size={16} />
        {label}
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={(e) => void choose(e)}
        />
      </label>
      {value && (
        <button type="button" onClick={() => onChange(null)}>
          Remove photo
        </button>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}

export function SetupFields({
  value,
  onChange,
  solar,
}: {
  value: Setup;
  onChange: (setup: Setup) => void;
  solar: boolean;
}) {
  const set = <K extends keyof Setup>(key: K, v: Setup[K]) =>
    onChange({ ...value, [key]: v });
  return (
    <>
      <div className="ux-form-grid">
        <label>
          City
          <select
            aria-label="City"
            value={value.city}
            onChange={(e) => set("city", e.target.value)}
          >
            {["Ahmedabad", "Surat", "Vadodara", "Rajkot", "Gandhinagar"].map(
              (c) => (
                <option key={c}>{c}</option>
              ),
            )}
          </select>
        </label>
        <label>
          Home type
          <select
            value={value.home_type}
            onChange={(e) => set("home_type", e.target.value)}
          >
            <option value="independent">Independent home</option>
            <option value="apartment">Apartment</option>
            <option value="bungalow">Bungalow</option>
          </select>
        </label>
        <label>
          People at home
          <input
            type="number"
            min="1"
            max="20"
            required
            value={value.occupants}
            onChange={(e) => set("occupants", Number(e.target.value))}
          />
        </label>
        <label>
          Monthly consumption (kWh)
          <input
            type="number"
            min="30"
            max="3000"
            required
            value={value.monthly_kwh}
            onChange={(e) => set("monthly_kwh", Number(e.target.value))}
          />
          <small>Find units consumed on your electricity bill.</small>
        </label>
        <label>
          Air conditioners
          <input
            type="number"
            min="0"
            max="8"
            value={value.ac_count}
            onChange={(e) => set("ac_count", Number(e.target.value))}
          />
        </label>
        <label>
          Your comparison rate (₹/kWh)
          <input
            type="number"
            min="0.5"
            max="30"
            step="0.01"
            required
            value={value.retail_rate}
            onChange={(e) => set("retail_rate", Number(e.target.value))}
          />
          <small>Use your bill's effective rate; editable anytime.</small>
        </label>
        {solar && (
          <>
            <label>
              Roof orientation
              <select
                value={value.orientation}
                onChange={(e) => set("orientation", e.target.value)}
              >
                {["south", "east", "west", "north"].map((d) => (
                  <option value={d} key={d}>
                    {d[0].toUpperCase() + d.slice(1)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Panel tilt (degrees)
              <input
                type="number"
                min="0"
                max="60"
                value={value.tilt}
                onChange={(e) => set("tilt", Number(e.target.value))}
              />
            </label>
          </>
        )}
      </div>
      <div className="ux-checks">
        <label>
          <input
            type="checkbox"
            checked={value.daytime_home}
            onChange={(e) => set("daytime_home", e.target.checked)}
          />
          Someone is usually home during the day
        </label>
        <label>
          <input
            type="checkbox"
            checked={value.has_ev}
            onChange={(e) => set("has_ev", e.target.checked)}
          />
          We charge an electric vehicle at home
        </label>
        <label>
          <input
            type="checkbox"
            checked={value.share_stats}
            onChange={(e) => set("share_stats", e.target.checked)}
          />
          Share household energy totals with the community
        </label>
      </div>
    </>
  );
}

export function AuthPage({
  perform,
  pending,
}: {
  perform: Perform;
  pending: boolean;
}) {
  const [signup, setSignup] = useState(false);
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("consumer");
  const [capacity, setCapacity] = useState(6);
  const [setup, setSetup] = useState(defaultSetup);
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (signup && step === 0) {
      setStep(1);
      return;
    }
    await perform(signup ? "/auth/register" : "/auth/login", {
      name,
      email,
      password,
      role,
      capacity_kw: capacity,
      ...(signup ? { setup } : {}),
    });
  }
  return (
    <div className="uw-login ux-auth">
      <section className="uw-login-story">
        <div className="uw-brand">
          <Zap />
          UrjaSetu
        </div>
        <div className="uw-eyebrow">GOOD ENERGY. SHARED LOCALLY.</div>
        <h1>
          Your sunshine.
          <br />
          Our brighter
          <br />
          <em>tomorrow.</em>
        </h1>
        <p>
          A neighbourhood where surplus solar finds a home. Your energy, your
          people, a little more possibility.
        </p>
        <div className="ux-sun-art" aria-hidden="true">
          <Sun />
          <span className="sun-house">⌂</span>
          <span className="sun-leaf">↗</span>
        </div>
        <small>
          Made for Gujarat · All times in IST
          <br />
          Energy flows through your community's distribution grid.
        </small>
      </section>
      <section className="uw-login-form">
        <div className="uw-eyebrow">YOUR ENERGY COMMUNITY</div>
        <h2>
          {signup
            ? step
              ? "Tell us about your home."
              : "Make yourself at home."
            : "A little sunshine awaits."}
        </h2>
        <p>
          {signup
            ? `Step ${step + 1} of 2 · ${step ? "A few details make your energy view personal." : "Start with your account."}`
            : "Sign in to your home, your trades and your community."}
        </p>
        <form onSubmit={(e) => void submit(e)}>
          {(!signup || step === 0) && (
            <>
              {signup && (
                <label>
                  Your name
                  <input
                    autoComplete="name"
                    required
                    minLength={2}
                    maxLength={80}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </label>
              )}
              <label>
                Email
                <input
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </label>
              <label>
                Password
                <input
                  type="password"
                  autoComplete={signup ? "new-password" : "current-password"}
                  minLength={10}
                  maxLength={128}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </label>
              {signup && (
                <>
                  <label>
                    Your energy setup
                    <select
                      value={role}
                      onChange={(e) => setRole(e.target.value)}
                    >
                      <option value="consumer">I buy energy · Consumer</option>
                      <option value="prosumer">
                        I have rooftop solar · Prosumer
                      </option>
                    </select>
                  </label>
                  {role === "prosumer" && (
                    <label>
                      Solar capacity (kW)
                      <input
                        type="number"
                        min="1"
                        max="15"
                        step="0.1"
                        required
                        value={capacity}
                        onChange={(e) => setCapacity(Number(e.target.value))}
                      />
                    </label>
                  )}
                </>
              )}
            </>
          )}
          {signup && step === 1 && (
            <>
              <SetupFields
                value={setup}
                onChange={setSetup}
                solar={role === "prosumer"}
              />
              <PhotoInput
                label="Add your profile photo"
                value={setup.avatar}
                onChange={(avatar) => setSetup({ ...setup, avatar })}
              />
              <p className="uw-hint ux-connection-note">
                Your dashboard starts with profile-based readings. Connect a
                meter in a future integration to replace estimates with
                measurements.
              </p>
            </>
          )}
          <button className="uw-primary" disabled={pending} type="submit">
            {pending
              ? "One moment…"
              : signup
                ? step
                  ? "Join the community"
                  : "Continue"
                : "Sign in"}
            <ArrowRight size={16} />
          </button>
          {signup && step === 1 && (
            <button type="button" onClick={() => setStep(0)}>
              Back to account
            </button>
          )}
        </form>
        <button
          className="ux-text-button"
          onClick={() => {
            setSignup(!signup);
            setStep(0);
          }}
        >
          {signup ? "Already a member? Sign in" : "New here? Create an account"}
        </button>
        {!signup && (
          <details className="ux-sample-access">
            <summary>Quick access accounts</summary>
            <p>Explore with Asha or Ravi. Password: Sunshine2026!</p>
            <div>
              {[
                { id: "asha", label: "Asha · Solar owner" },
                { id: "ravi", label: "Ravi · Energy buyer" },
                { id: "priya", label: "Priya · 7.5 kW Solar" },
                { id: "ananya", label: "Ananya · Apartment consumer" },
                { id: "operator", label: "Community operator" },
              ].map((account) => (
                <button
                  key={account.id}
                  onClick={() => {
                    setEmail(`${account.id}@urjasetu.demo`);
                    setPassword("Sunshine2026!");
                  }}
                >
                  {account.label}
                </button>
              ))}
            </div>
          </details>
        )}
      </section>
    </div>
  );
}

export function ProfilePage({
  data,
  perform,
  pending,
}: {
  data: Experience;
  perform: Perform;
  pending: boolean;
}) {
  const [period, setPeriod] = useState<Period>("month");
  const [setup, setSetup] = useState(data.profile);
  const days = period === "day" ? 1 : period === "week" ? 7 : 30;
  return (
    <>
      <Heading
        title="A home for your energy."
        subtitle="Your setup, your progress, and the difference you make."
      />
      <Card className="ux-profile-banner">
        <Avatar name={data.user.name} src={data.profile.avatar} size="large" />
        <div>
          <h2>{data.user.name}</h2>
          <p>{data.user.email}</p>
          <span>
            {data.profile.city} · {data.user.role} ·{" "}
            {fmt(data.sites[0]?.capacity_kw)} kW rooftop
          </span>
        </div>
        <ShieldCheck />
        <div className="ux-profile-total">
          <small>Lifetime energy exchanged</small>
          <strong>{fmt(data.portfolio.traded_kwh)} kWh</strong>
        </div>
      </Card>
      <div className="ux-section-line">
        <h2>Your energy footprint</h2>
        <PeriodTabs value={period} onChange={setPeriod} />
      </div>
      <MetricCards metrics={data.periods[period]} />
      <MetricCards metrics={data.periods[period]} kind="money" />
      <Card
        title="Your buying & selling"
        note="Delivered energy in the selected period"
      >
        <div className="ux-detail-stats">
          <div>
            <small>Energy bought</small>
            <strong>
              {fmt(data.periods[period].bought_kwh)} <span>kWh</span>
            </strong>
          </div>
          <div>
            <small>Energy sold</small>
            <strong>
              {fmt(data.periods[period].sold_kwh)} <span>kWh</span>
            </strong>
          </div>
        </div>
      </Card>
      <Card title="Your energy history" note="Daily totals in kWh · IST">
        <HistoryChart data={data.daily.slice(-days)} />
      </Card>
      <Card
        title="Make it yours"
        note="Changes apply to future household readings. Existing accounting records stay attached to their original delivery evidence."
      >
        <form
          className="ux-profile-form"
          onSubmit={async (e) => {
            e.preventDefault();
            await perform(
              "/workspace/profile",
              setup,
              "Your household profile is updated.",
              "PUT",
            );
          }}
        >
          <div className="ux-photo-pair">
            <PhotoInput
              label="Your profile photo"
              value={setup.avatar}
              onChange={(avatar) => setSetup({ ...setup, avatar })}
            />
            <PhotoInput
              label="Your home or rooftop photo"
              large
              value={setup.photo}
              onChange={(photo) => setSetup({ ...setup, photo })}
            />
          </div>
          <SetupFields
            value={setup}
            onChange={setSetup}
            solar={data.user.role === "prosumer"}
          />
          <button className="uw-primary" disabled={pending}>
            Save household settings
          </button>
        </form>
      </Card>
      <Card title="Connections & preferences">
        <div className="ux-connection-grid">
          <div>
            <h3>Energy data</h3>
            <p>Profile-based readings · Meter not connected</p>
            <small>
              Demand follows your monthly usage, occupants and appliances. Solar
              follows your rooftop setup and local daylight. Five-second and
              one-minute curves use your current profile; completed 15-minute
              records preserve history.
            </small>
          </div>
          <div>
            <h3>Savings benchmark</h3>
            <p>₹{fmt(data.profile.retail_rate)}/kWh · Your comparison rate</p>
            <small>
              Figures compare energy costs with this rate; they are not a DISCOM
              bill. Sales income is shown separately from savings.
            </small>
          </div>
          <div>
            <h3>Settlement network</h3>
            <p>Local EVM blockchain · INR accounting</p>
            <small>
              Receipts verify stored settlement records. The account ledger does
              not move bank funds or bill your utility.
            </small>
          </div>
          <div>
            <h3>Location & time</h3>
            <p>Asia/Kolkata · Indian Standard Time</p>
            <small>
              All charts, delivery slots and activity timestamps use IST.
            </small>
          </div>
        </div>
      </Card>
    </>
  );
}
