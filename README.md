# 📦 StockAlert

**Automated Inventory Reorder Point Calculator**

StockAlert is a Python tool that analyzes sales data and automatically calculates the optimal reorder point for inventory items — helping retail stores, pharmacies, and restaurants avoid stockouts and over-ordering.

---

## 🔍 What Problem Does It Solve?

A customer walks into a pharmacy asking for a product. The pharmacist says: *"Sorry, we're out of stock."* That's lost revenue and a damaged customer relationship.

StockAlert prevents this by analyzing historical sales data and telling the business exactly when to reorder — before it's too late.

---

## ✨ Features

- **Automated data loading** — upload your CSV directly in Jupyter with a single click
- **Smart data cleaning** — detects and handles duplicates, null values, and outliers automatically using IQR
- **Statistical ROP calculation** — uses the industry-standard formula with Z-score safety stock (95% confidence level)
- **Flexible stock monitoring** — reads current inventory from your dataset or accepts manual input
- **Date-aware** — uses the most recent inventory reading when multiple records exist
- **Case-insensitive column matching** — works with `Units Sold`, `units sold`, or `UNITS SOLD`

---

## 📊 How It Works

```
Upload CSV → Select Product → Clean Data → Calculate ROP → Monitor Stock Level → Alert
```

The core formula:

```
Safety Stock = Z × σ × √(Lead Time)
ROP = (Average Daily Sales × Lead Time) + Safety Stock
```

Where Z = 1.65 (95% service level), σ = standard deviation of sales.

---

## 🚀 Getting Started

**Requirements**
```
Python 3.8+
pandas
numpy
ipywidgets
```

**Installation**
```bash
git clone https://github.com/YourUsername/StockAlert.git
cd StockAlert
pip install pandas numpy ipywidgets
```

**Run**

Open `StockAlert.ipynb` in Jupyter and run `main()`.

The program will guide you through:
1. Uploading your CSV file
2. Entering your product column name and product ID
3. Entering your sales column name
4. Entering the lead time (days to receive a new order)
5. Choosing how to provide the current stock level

---

## 📁 Dataset Requirements

Your CSV should contain at minimum:
| Column | Description | Example |
|--------|-------------|---------|
| Product ID column | Unique identifier for each product | `P0001` |
| Sales column | Units sold per record | `Units Sold` |
| Inventory column *(optional)* | Current stock level | `Inventory Level` |
| Date column *(optional)* | Date of each record | `Date` |

Column names are flexible — you enter the exact names from your own dataset.

---

## 💡 Example Output

```
✅  Stock is OK
    Current stock : 850 units
    Reorder point : 632.7 units
    → 217.3 units above reorder point

⚠️  REORDER ALERT
    Current stock : 267 units
    Reorder point : 632.7 units
    → Place a new order now
```

---

## 🗺️ Roadmap

- [x] CSV file upload with Jupyter widget
- [x] Automated data cleaning (duplicates, nulls, outliers)
- [x] Statistical ROP calculation with Z-score safety stock
- [x] Stock level monitoring with reorder alerts
- [ ] Direct database connectivity (SQLAlchemy)
- [ ] Automated scheduling — daily stock checks, quarterly ROP recalculation
- [ ] Web interface (FastAPI + React)
- [ ] Seasonal demand adjustment using ML

---

## 🧑‍💻 Author

**Mustafa Ismail ** — self-taught developer focused on data analysis and automation tools.

[GitHub](https://github.com/MustafaSameh) · [LinkedIn](https://www.linkedin.com/in/mustafa-ismail-429267377/)

---

## 📄 License

MIT License — free to use and modify.
