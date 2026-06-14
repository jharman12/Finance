# Finance App Seeds

This folder contains CSV seed data for development and testing. These files are committed to git so the whole team can work from the same starting dataset.

## Files

| File | Contents |
|------|----------|
| `categories.csv` | All expense and income categories |
| `transactions.csv` | Sample transactions (May–June 2026) |
| `recurring_items.csv` | Recurring income/expense definitions |
| `budgets.csv` | Monthly budget targets |

## Usage

### Load seed data (fresh start)
```bash
python manage.py import --clear
```

### Load seed data on top of existing data
```bash
python manage.py import
```

### Save your current data as the new shared seed
```bash
python manage.py export
git add seeds/
git commit -m "chore: update seed data"
```

### Check what's in the current database
```bash
python manage.py status
```

## Rules

- The `.db` file is git-ignored and **never committed**
- The `seeds/` CSVs **are** committed
- To share new test data: export, then commit and push the CSVs
- End users install the app fresh with no seeds — they start with an empty database
