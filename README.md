# Toll Nominator — Linkt / CityLink Victoria

Automatically reads toll infringement invoices using Claude Vision, looks up the nominated driver from your CSV, fills the Linkt nomination form in a real browser, and pauses for your review before submitting.

---

## Setup

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Install Playwright browsers
```bash
playwright install chromium
```

### 3. Set your Anthropic API key
```bash
# macOS / Linux
export ANTHROPIC_API_KEY=sk-ant-...

# Windows
set ANTHROPIC_API_KEY=sk-ant-...
```

### 4. Configure your drivers CSV
Edit `drivers.csv` — one row per vehicle. Required columns:

| Column | Description |
|---|---|
| registration | Number plate e.g. ABC123 |
| first_name | Driver's first name |
| last_name | Driver's last name |
| licence_number | Drivers licence number |
| licence_state | State of licence e.g. VIC |
| date_of_birth | DD/MM/YYYY |
| email | Driver's email |
| phone | Driver's phone |
| address | Street address |
| suburb | Suburb |
| postcode | Postcode |
| state | State e.g. VIC |

### 5. Run the app
```bash
python app.py
```

Open your browser at: **http://localhost:5000**

---

## How It Works

1. **Upload** — Drop or select your toll invoice JPG/PNG
2. **Analyse** — Claude Vision extracts all toll fields from the image
3. **Review** — See extracted data + matched driver. Edit any field if needed
4. **Automate** — App opens Chromium, fills every form field automatically
5. **Review & Submit** — Check the browser, then click Submit in the app

---

## Updating the Nomination URL

If Linkt changes their URL, update `LINKT_NOMINATION_URL` in `automation.py`:
```python
LINKT_NOMINATION_URL = "https://www.linkt.com.au/nominate-a-driver"
```

Some infringement notices include a unique URL — the app will use that if extracted.

---

## Customising Form Selectors

The automation uses CSS selectors to find form fields. If Linkt's form changes, update the selectors in `automation.py` inside `fill_nomination_form()`.

To find the right selectors: open the Linkt form in Chrome → right-click a field → Inspect → copy the `name` or `id` attribute.
