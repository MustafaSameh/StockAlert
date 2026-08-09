import pandas as pd
import numpy as np
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from src.data_utils import data_sanitizer, find_date_column

class StockAlert:
    # Initialize the class with the required parameters
    def __init__(self,targeted_sales,sales_column,lead_time, restock_days = 0 , inventory_column = None , product_column=None):
        # __init__ runs automatically when you create the object
        # it just stores the shared data so you don't pass it everywhere
        self.targeted_sales     = targeted_sales
        self.sales_column       = sales_column
        self.lead_time          = lead_time
        self.restock_days       = restock_days
        self.inventory_column   = inventory_column
        self.rop                = None   # calculated later
        self.avg_sales          = None
        self.std_dev            = None
        self.product_column     = product_column
    
    def clean(self):
        # no need to pass targeted_sales — it's already stored in self
        self.targeted_sales = data_sanitizer(
            self.targeted_sales, 
            self.sales_column
    )

    def calculate_rop(self):
        avg = self.targeted_sales[self.sales_column].mean()
        std = self.targeted_sales[self.sales_column].std()

        if pd.isna(std):
            std = 0.0
            
        safety_stock = 1.65 * std * np.sqrt(self.lead_time)        
        self.rop = (avg * self.lead_time) + safety_stock
        self.avg_sales = avg
        self.std_dev = std
        
        return self.rop, self.avg_sales, self.std_dev

    def calculate_all_rops(self):
        results = []
        
        for product in self.targeted_sales[self.product_column].unique():
            product_df = self.targeted_sales[self.targeted_sales[self.product_column] == product].copy()
            product_df = data_sanitizer(product_df, self.sales_column)
            
            avg   = product_df[self.sales_column].mean()
            std   = product_df[self.sales_column].std()
            if pd.isna(std): std = 0.0
            current_lt = product_df['Lead_Time'].iloc[0] if 'Lead_Time' in product_df.columns else (self.lead_time or 3)
            safety_stock = 1.65 * std * np.sqrt(current_lt)   # ← use current_lt
            rop = (avg * current_lt) + safety_stock   
            
            # Get latest inventory level for this product
            date_col = find_date_column(product_df)
            latest   = product_df.sort_values(date_col).iloc[-1] if date_col else product_df.iloc[-1]
            current_stock = latest[self.inventory_column]
            status = "⚠️ REORDER" if current_stock <= rop else "✅ OK"
            
            results.append({
                "Product":        product,
                "Avg Daily Sales": round(avg, 1),
                "ROP":            round(rop, 1),
                "Current Stock":  current_stock,
                "Status":         status
            })
        
        return pd.DataFrame(results)

    def calculate_days_of_stock(self, order_quantity: int) -> str:
        """Returns how many days a specific order quantity will last."""
        days = (order_quantity - self.rop) / self.avg_sales if self.avg_sales != 0 else 0
        return f"→ {order_quantity} units will last approximately {days:.1f} days."

    def calculate_quantity_for_days(self, target_days: int) -> str:
        """Returns the recommended order quantity to last a specific number of days."""
        qty = self.rop + (self.avg_sales * target_days)
        return f"→ Recommended order quantity for {target_days} days: {qty:.1f} units."

    def check_stock(self , current_stock: float):
        if current_stock <= self.rop:
            return f"⚠️ REORDER ALERT: Current stock ({current_stock}) is at or below ROP ({self.rop:.1f})"
        else:
            buffer = current_stock - self.rop
            return f"✅ Stock OK: {buffer:.1f} units above ROP ({self.rop:.1f})"

    def daily_stock_check(self):
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 🔄 Daily stock check...")
        
        if self.inventory_column is None:
                print("  ℹ️  No inventory column configured — skipping automated check")
                return
        try:
            date_col  = find_date_column(self.targeted_sales)
            latest_row = (
                self.targeted_sales.sort_values(date_col).iloc[-1]
                if date_col else self.targeted_sales.iloc[-1]
            )
            current_stock = latest_row[self.inventory_column]
            if current_stock <= self.rop:
                print(f"  ⚠️  REORDER ALERT")
                print(f"      Current stock : {current_stock} units")
                print(f"      Reorder point : {self.rop:.1f} units")
                print(f"      → Place a new order now")
            else:
                print(f"  ✅  Stock OK — {current_stock - self.rop:.1f} units above ROP")
        except Exception as e:
            print(f"  ❌ Daily check failed: {e}")

    def recalculate_rop(self):
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 📊 Recalculating ROP...")
        try:
            self.clean()
            new_rop, new_avg, new_std = self.calculate_rop()
            print(f"  ✅  New ROP : {new_rop:.1f} units")
            print(f"      Avg     : {new_avg:.1f} | Std dev: {new_std:.1f}")
            return new_rop
        except Exception as e:
            print(f"  ❌ Recalculation failed: {e}")

    def start_scheduler(self, review_period):
        review_weeks = max(1, review_period // 7)
        scheduler    = BackgroundScheduler()
    
        scheduler.add_job(
            self.daily_stock_check,
            trigger='cron', hour=8, id='daily_check'
        )
        scheduler.add_job(
            self.recalculate_rop,
            trigger='interval', weeks=review_weeks, id='rop_recalc'
        )
        scheduler.start()
        print(f"✅  Scheduler started")
        print(f"    Daily stock check  : every day at 8:00 AM")
        print(f"    ROP recalculation  : every {review_weeks} weeks")
        return scheduler