Read one broker page of account transaction history. Obtain account_id_key from accounts_list; optional start_date and end_date must be supplied together. Continue with the returned marker and the same filters. Transaction boundaries are inclusive, so repeated boundary records are preserved; consumers handle any deduplication. Use transactions_get for details of a returned transaction.

Synthetic argument example:

```json
{
  "account_id_key": "synthetic-key",
  "request": {
    "count": 25,
    "sort_order": "DESC"
  }
}
```
