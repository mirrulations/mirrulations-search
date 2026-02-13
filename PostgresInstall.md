# PostgreSQL Quick Start Guide

**Run these commands from the `dev/` folder**

---

## Start PostgreSQL

```bash
docker compose up -d postgres
```

---

## Verify PostgreSQL is Running

### Quick Check
```bash
docker compose ps postgres
```

### Detailed Verification
```bash
echo "=== Container Status ==="
docker ps | grep postgres
echo ""
echo "=== Test Connection ==="
CONTAINER_NAME=$(docker ps | grep postgres | awk '{print $NF}')
docker exec $CONTAINER_NAME psql -U postgres -d postgres -c "SELECT version();"
echo ""
echo "=== Database Tables ==="
docker exec $CONTAINER_NAME psql -U postgres -d postgres -c "\dt"
```

---

## Useful Commands

### Stop PostgreSQL
```bash
docker compose down postgres
```

### View Logs
```bash
docker compose logs postgres
```

### Connect to PostgreSQL Shell
```bash
CONTAINER_NAME=$(docker ps | grep postgres | awk '{print $NF}')
docker exec -it $CONTAINER_NAME psql -U postgres -d postgres
```

### Check Container Health
```bash
docker ps | grep postgres
```
Look for `(healthy)` status

### Restart PostgreSQL
```bash
docker compose restart postgres
```

---

## Notes

- PostgreSQL runs on port `5432`
- Default database: `postgres`
- Default user: `postgres`
- Password is set in `dev/.env` file
