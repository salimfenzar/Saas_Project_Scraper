# CAO Monitor Backend

Deze backend heeft één handmatige pipeline voor de volledige flow:

1. FNV CAO-pagina's crawlen.
2. PDF-links vinden.
3. PDF's downloaden en ontdubbelen met SHA-256.
4. CAO's, versies en documenten opslaan in Supabase.
5. Salarispagina's herkennen.
6. Uur-, maand- en jaarbedragen automatisch onderscheiden.
7. Salaristabellen en regels opslaan.
8. Data via eenvoudige React-endpoints beschikbaar maken.

## 1. Database eenmalig schoon opbouwen

Open in Supabase **SQL Editor**, open `../database/reset_and_create.sql`, plak de volledige inhoud en klik op **Run**.

Dit verwijdert de bestaande CAO-monitor-tabellen en maakt ze opnieuw aan. Gebruik dit dus alleen wanneer de huidige testdata weg mag.

## 2. Omgevingsvariabelen

```bash
cd backend
cp .env.example .env
```

Vul in `.env` in:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

De service-role key hoort alleen in de backend. Zet deze nooit in React of in GitHub.

## 3. Installeren in GitHub Codespaces

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open daarna de Codespaces-poort 8000 en ga naar `/docs`.

## 4. Eerste veilige test met één CAO

Open in Swagger:

`POST /api/pipeline/run`

Body:

```json
{
  "max_caos": 1,
  "max_pages": 150,
  "reprocess_existing": false
}
```

De response bevat een `run_id` en `status_url`. Open daarna:

`GET /api/pipeline/runs/{run_id}`

Wacht tot de status `completed` of `partial` is.

## 5. Daarna de volledige crawler starten

```json
{
  "max_caos": null,
  "max_pages": 500,
  "reprocess_existing": false
}
```

De POST-route antwoordt direct en de verwerking gaat op de achtergrond verder. Je React-knop hoeft dus niet minutenlang te wachten.

## React-endpoints

- `GET /api/dashboard/summary`
- `GET /api/caos`
- `GET /api/caos/{cao_id}`
- `GET /api/caos/{cao_id}/salary-tables`
- `POST /api/pipeline/run`
- `GET /api/pipeline/runs/{run_id}`

Voorbeeld:

```ts
const response = await fetch(`${API_URL}/api/caos`);
const data = await response.json();
console.log(data.items);
```

Pipeline starten:

```ts
const response = await fetch(`${API_URL}/api/pipeline/run`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    max_caos: null,
    max_pages: 500,
    reprocess_existing: false,
  }),
});

const run = await response.json();
console.log(run.status_url);
```

## Database later opnieuw leegmaken

Standaard is de resetroute uitgeschakeld. Tijdelijk in `.env`:

```env
ALLOW_DATABASE_RESET=true
ADMIN_TOKEN=een-lange-geheime-token
```

Daarna:

```bash
curl -X POST "http://localhost:8000/api/admin/reset-data" \
  -H "X-Admin-Token: een-lange-geheime-token"
```

Zet `ALLOW_DATABASE_RESET` daarna weer op `false`.

## Belangrijke beperking

`pdfplumber` werkt goed met machinegegenereerde PDF's. Een ingescande PDF zonder tekstlaag wordt wel als document opgeslagen, maar krijgt geen salaristabellen. Zo'n document verschijnt in `processing_runs.raw_output.warnings` en kan later met OCR worden toegevoegd.
