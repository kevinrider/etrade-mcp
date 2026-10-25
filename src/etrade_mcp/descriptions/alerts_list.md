Read account/stock alerts with optional category, status, count, ordering, and search filters. Returns alert IDs and summaries for alerts_get. Broker defaults apply when filters are omitted; the adapter does not automatically fetch additional results. Does not delete alerts or change trading permissions.

Synthetic argument example:

```json
{
  "request": {
    "count": 25,
    "status": "UNREAD"
  }
}
```
