# Database Setup Guide

## Overview

The backend now uses SQLite database (or PostgreSQL if `DATABASE_URL` environment variable is set) to store:
- **Calculation History**: All calculations are automatically saved
- **Saved Addresses**: Frequently used delivery addresses

## Database Configuration

### SQLite (Default - Local Development)

The app automatically creates a SQLite database file `buyee_calculator.db` in the project directory.

**No setup required** - it works out of the box!

### PostgreSQL (Production - Render/Railway)

For production deployments, set the `DATABASE_URL` environment variable:

**On Render.com:**
1. Go to your service → **Environment**
2. Add environment variable:
   - Key: `DATABASE_URL`
   - Value: Your PostgreSQL connection string (e.g., `postgresql://user:pass@host:5432/dbname`)

**On Railway.app:**
1. Add PostgreSQL service
2. Railway automatically sets `DATABASE_URL` environment variable
3. Your Flask app will automatically use it

## Database Tables

### `calculation_history`
Stores all calculation results:
- Link, item name, shipping method
- All cost breakdowns (JPY and USD)
- Destination address and ZIP
- Timestamp

### `saved_addresses`
Stores frequently used addresses:
- Address and ZIP code
- Optional name/label
- Usage count and last used timestamp

## API Endpoints

### Get Calculation History
```
GET /api/history?limit=50&offset=0
```

### Get Specific History Item
```
GET /api/history/<id>
```

### Get Saved Addresses
```
GET /api/addresses
```

### Save Address
```
POST /api/addresses
Body: {
  "address": "123 Main St",
  "zip_code": "12345",
  "name": "Home" (optional)
}
```

### Delete Address
```
DELETE /api/addresses/<id>
```

### Get Statistics
```
GET /api/stats
Returns: Total calculations, addresses, spending, shipping method usage
```

## Automatic Saving

- **Calculations are automatically saved** to database when you use `/calculate` or `/calculate_batch`
- To disable saving, pass `"save_to_db": false` in the request body

## Database File Location

- **Local**: `buyee_calculator.db` in project root
- **Render**: Uses PostgreSQL if `DATABASE_URL` is set
- **Railway**: Uses PostgreSQL service

## Backup

### SQLite Backup
```bash
# Copy the database file
cp buyee_calculator.db buyee_calculator.db.backup
```

### PostgreSQL Backup (Render/Railway)
```bash
# Export database
pg_dump $DATABASE_URL > backup.sql

# Restore
psql $DATABASE_URL < backup.sql
```

## Reset Database

**⚠️ Warning: This deletes all data!**

```python
# In Python shell or script
from app import app, db
with app.app_context():
    db.drop_all()
    db.create_all()
```

## Troubleshooting

### Database Locked Error
- Make sure only one instance of the app is running
- Check for file permissions on `buyee_calculator.db`

### Migration Issues
- Delete `buyee_calculator.db` and restart app (tables will be recreated)
- Or use Flask-Migrate for proper migrations (not included by default)

### Connection String Format
- SQLite: `sqlite:///path/to/db.db`
- PostgreSQL: `postgresql://user:password@host:port/dbname`
- Render auto-formats PostgreSQL URLs correctly
