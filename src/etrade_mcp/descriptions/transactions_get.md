Read details of one transaction identified by its account and transaction ID. Obtain account_id_key from accounts_list and transaction_id from transactions_list; preserve broker store_id if needed. Returns the complete modeled transaction detail. This is history lookup, not current order-status monitoring or execution.

Synthetic argument example:

```json
{
  "account_id_key": "synthetic-key",
  "transaction_id": "synthetic-transaction"
}
```
