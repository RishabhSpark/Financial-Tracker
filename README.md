# Financial-Tracker

```bash
git clone https://github.com/RishabhSpark/Financial-Tracker.git
cd Financial-Tracker
uv pip install -r requirements.txt
```

```
{
    client_name:,
    po_id:,
    amount:
    status:,
    payment_terms:,
    payment_divi: monthly,
    start_date:,
    end_date:,
    payment_divisions:          # Periodic (divide by 3 jaise)
    {
        payment_1:{
            date:,
            amount:
        },
        payment_2:{
            date:,
            amount:
        },
        payment_3:{
            date:,
            amount:
        }
    },

    client_name:,
    po_id:,
    amount:
    status:,
    payment_terms:,
    payment_divisions:,
    start_date:,
    end_date:,
    payment_divisions:      # Distributed
    {
        payment_1:{
            date:,
            amount
        },
        payment_2:{
            date:,
            amount
        },
        payment_3:{
            date:,
            amount
        }
    },
    client_name:,
    po_id:,
    amount:
    status:,
    payment_terms:,
    payment_
    start_date:,
    end_date:,
    payment_divisions:          # Milestone
    {
        payment_1:{             #Initial 
            date:,
            amount
        },
        payment_2:{             # Milestone1
            date:,
            amount
        },
        payment_3:{             # Milestone2
            date:,
            amount
        }
    }
}

```

```
✅ 1. po_summary.csv
Contains general information about each Purchase Order.

Columns:
- client_name
- po_id
- amount
- status
- payment_terms
- payment_divi (e.g., monthly, distributed, milestone — optional, if available)
- start_date
- end_date

✅ 2. po_payments.csv
Contains the payment breakdown for each PO.

Columns:
- po_id
- payment_label (e.g., payment_1, payment_2, etc.)
- date
- amount
- milestone_label (optional — e.g., Initial, Milestone1, only filled if known)

```