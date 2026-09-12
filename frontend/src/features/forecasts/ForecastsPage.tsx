import { useState } from "react";
import { Sun, TrendingUp, Activity } from "lucide-react";
import { PageHeader, Card, Stat, Tabs, Badge, Note } from "../../components/ui";
import EnergyChart from "../../components/EnergyChart";
export default function ForecastsPage() {
  const [range, setRange] = useState("Today");
  return (
    <>
      <PageHeader
        eyebrow="AHEAD OF THE ENERGY CURVE"
        title="A brighter outlook."
        description="Plan tomorrow’s delivery with generation, demand and exportable surplus."
      />
      <div className="stats-grid three">
        <Stat
          label="Forecast generation"
          value="96.4"
          unit="kWh"
          note="Illustrative next-day total"
          icon={<Sun size={20} />}
        />
        <Stat
          label="Exportable surplus"
          value="38.2"
          unit="kWh"
          note="Illustrative available energy"
          icon={<TrendingUp size={20} />}
        />
        <Stat
          label="Forecast confidence"
          value="86"
          unit="%"
          note="Illustrative provider confidence"
          icon={<Activity size={20} />}
        />
      </div>
      <Card
        title="Tomorrow’s energy profile"
        subtitle="Illustrative solar and load forecast · 13 Sep 2026 · IST"
        action={
          <Tabs
            items={["Today", "Morning", "Afternoon"]}
            value={range}
            onChange={setRange}
          />
        }
      >
        <EnergyChart range={range} />
      </Card>
      <Card
        title="Delivery-window outlook"
        subtitle="Illustrative forecast · provider: baseline · forecasts are estimates"
      >
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Delivery window · IST</th>
                <th>Generation</th>
                <th>Demand</th>
                <th>Exportable surplus</th>
                <th>Outlook</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["06:00–09:00", "8.4", "12.1", "0.0", "Deficit expected"],
                ["09:00–12:00", "28.6", "13.4", "15.2", "Surplus expected"],
                ["12:00–15:00", "36.2", "17.0", "19.2", "Surplus expected"],
                ["15:00–18:00", "23.2", "19.4", "3.8", "Surplus expected"],
              ].map((r) => (
                <tr key={r[0]}>
                  <td>
                    <strong>13 Sep · {r[0]}</strong>
                  </td>
                  {r.slice(1, 4).map((v, i) => (
                    <td key={i}>{v} kWh</td>
                  ))}
                  <td>
                    <Badge
                      tone={r[4].startsWith("Deficit") ? "amber" : "green"}
                    >
                      {r[4]}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Note>
        The backend owns forecast selection, confidence and exportable surplus.
        The frontend never increases sell eligibility based on an illustrative
        chart.
      </Note>
    </>
  );
}
