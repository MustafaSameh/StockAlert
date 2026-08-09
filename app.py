# Import Required Libraries 
from prophet import Prophet
import pandas as pd
import streamlit as st 
#-----------------------
# Backend #
#-----------------------
from src.stock_alert import StockAlert
from src.data_utils import find_date_column, sql_connection, manual_rop_calculator
# ==========================================
# 🎨 FRONTEND UI HELPERS
# ==========================================

def display_bulk_results(results_df, review_period, alert, session_key):
    """Reusable UI component for displaying bulk analysis results."""
    st.write("### 3. Bulk Results")
    st.success(f"Scheduler activated: Recalculating every {max(1, review_period // 7)} weeks.")

    filter_option = st.radio("Show:", ["All Products", "Needs Reorder Only", "OK Only"], horizontal=True, key=f"filter_{session_key}")
    
    if filter_option == "Needs Reorder Only":
        display_df = results_df[results_df["Status"] == "⚠️ REORDER"]
    elif filter_option == "OK Only":
        display_df = results_df[results_df["Status"] == "✅ OK"]
    else:
        display_df = results_df
        
    st.dataframe(display_df, use_container_width=True)
    st.metric("Products Needing Urgent Reorder", len(results_df[results_df["Status"] == "⚠️ REORDER"]))
    
    st.session_state[session_key] = alert

def render_manual_tab():
    st.header("Manual ROP Calculator")
    st.write("Just enter your numbers and we will calculate the ROP.")
    
    col1, col2 = st.columns(2)
    with col1:
        current_stock = st.number_input("Current Stock:", min_value=0, step=1)
        std_dev = st.number_input("Standard Deviation of Sales:", min_value=0.0)
    with col2:
        avg_sales = st.number_input("Average Sales:", min_value=0.0)
        lead_time = st.number_input("Lead Time (Days):", min_value=0, step=1)
        
    if st.button("Calculate Manual ROP"):
        result_text = manual_rop_calculator(current_stock, avg_sales, std_dev, lead_time)
        st.info(result_text)

def handle_single_product():

    data_source = st.radio("Choose your data source:", ["Upload Dataset (CSV)", "Connect to Database"])
                
    if data_source == "Upload Dataset (CSV)":
        st.subheader("Upload your CSV file")
        uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
        
        if uploaded_file is not None:
            # Display the dataframe as you designed in the wireframe
            df = pd.read_csv(uploaded_file) 
            st.dataframe(df.head()) 
            st.write("### Please fill these fields:")
            col_a, col_b = st.columns(2)
            with col_a:
                product_name = st.text_input("Product Name:") 
                review_period = st.number_input("Review Period (Days):", value=90)
            with col_b:
                sales_column = st.text_input("Sales Column Name (e.g., Units Sold):")
                product_column = st.text_input("Product Column Name:")
                lead_time_auto = st.number_input("Lead Time:", min_value=0)

            st.session_state['saved_sales_col'] = sales_column
            st.session_state['saved_leadtime'] = lead_time_auto
            st.session_state['saved_product_name'] = product_name
            # Sub-branch for stock level choice 
            stock_choice = st.radio("How to check current stock?", ["Manual Stock Level", "From Column"])
            if stock_choice == "Manual Stock Level":
                manual_stock = st.number_input("Enter current stock:")
            else:
                stock_column = st.text_input("Enter stock column name:")
                
            if st.button("Run Automatic Analysis"):
                # TODO: Initialize StockAlert class and run logic here!
                targeted = df[df[product_column] == product_name].copy()
                alert = StockAlert(targeted_sales=targeted, sales_column=sales_column, lead_time=lead_time_auto)
                st.session_state['my_saved_df'] = targeted
                alert.clean()
                calculated_rop, calculated_avg, calculated_std = alert.calculate_rop()
                if stock_choice == "Manual Stock Level":
                    current_stock = manual_stock
                else:
                    # Grab the very last row of the dataset and look at the stock column
                    current_stock = df.iloc[-1][stock_column]
                    
                # 4. Check the stock status
                result_text = alert.check_stock(current_stock)

                alert.start_scheduler(review_period)
                # 5. Display the final results beautifully on the screen!
                st.write(f"**Calculated ROP:** {calculated_rop:.1f} units")
                st.write(f"**(Avg Sales:** {calculated_avg:.1f} | **Std Dev:** {calculated_std:.1f})")
                st.info(result_text)
                st.success("Backend automated analysis will appear here.")
                st.success(f"Scheduler activated: ROP will recalculate every {max(1, review_period // 7)} weeks.")
                if st.button("🔄 Refresh Stock Status"):
                    if 'my_saved_df' in st.session_state and 'saved_sales_col' in st.session_state:
                        alert = StockAlert(
                        targeted_sales=st.session_state['my_saved_df'], 
                        sales_column=st.session_state['saved_sales_col'],
                        lead_time=st.session_state.get('saved_leadtime', 0)
                        )
                        alert.clean()
                        alert.calculate_rop()
                        st.success("Stock status recalculated successfully!")
                else:
                    st.warning("No data found to refresh. Please run an analysis first.") 

    elif data_source == "Connect to Database":
        st.subheader("Connect to your Database")
        
        db_col1, db_col2 = st.columns(2)
        with db_col1:
            db_type = st.selectbox("Database Type:", ["mysql", "postgresql", "sqlite"])
            db_port = st.text_input("Port (e.g., 3306 or 5432):")
            db_pass = st.text_input("Password:", type="password")
            # NEW: Missing dataconfig inputs
            sales_table = st.text_input("Sales Table Name:")
            product_name = st.text_input("Product Name:")
        with db_col2:
            db_host = st.text_input("Host (e.g., localhost):")
            db_user = st.text_input("Username:")
            db_name = st.text_input("Database Name:")
            # NEW: Missing dataconfig inputs
            product_column = st.text_input("Product Column Name:")
            sales_column = st.text_input("Sales Column Name (e.g., Units Sold):")
            lead_time_db = st.number_input("Lead Time (Days):", min_value=0)
            review_period = st.number_input("Review Period (Days):", value=90)
                
        inventory_col_db = st.text_input("Inventory Column Name (for current stock):")

        if st.button("Connect & Analyze"):
            try:
                df = sql_connection(db_type, db_host, db_port, db_user, db_pass, db_name, sales_table, product_column, product_name)
                targeted = df[df[product_column] == product_name].copy()
                st.session_state['my_saved_df'] = targeted
                st.session_state['saved_product_name'] = product_name
                st.session_state['saved_leadtime'] = lead_time_db 
                st.session_state['saved_sales_col'] = sales_column
                alert = StockAlert(targeted_sales=targeted, sales_column=sales_column, lead_time=lead_time_db)
                alert.clean()
                calculated_rop, calculated_avg, calculated_std = alert.calculate_rop()
                
                # Get current stock from inventory column
                date_col = find_date_column(df)
                latest_row = df.sort_values(date_col).iloc[-1] if date_col else df.iloc[-1]
                current_stock = latest_row[inventory_col_db]
                
                result_text = alert.check_stock(current_stock)
                st.write(f"**Calculated ROP:** {calculated_rop:.1f} units")
                st.info(result_text)
                alert.start_scheduler(review_period)
                st.success(f"Scheduler activated: ROP will recalculate every {max(1, review_period // 7)} weeks.")
            except Exception as e:
                st.error(f"Error: {e}")               

def handle_bulk_products():
    st.subheader("Bulk Automatic ROP Calculation")
    data_source = st.radio("Choose your data source:", ["Upload Dataset (CSV)", "Connect to Database"])
            
    if data_source == "Upload Dataset (CSV)":
        st.subheader("Upload your CSV file")
        uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
        calculated_rop = None

        if uploaded_file is not None:
            # Display the dataframe as you designed in the wireframe
            df = pd.read_csv(uploaded_file) 
            st.dataframe(df.head()) 
            st.write("### Please fill these fields:")

            col_a, col_b = st.columns(2)
            with col_a:
                review_period = st.number_input("Review Period (Days):", value=90)
                sales_column = st.text_input("Sales Column Name (e.g., Units Sold):")
                product_column = st.text_input("Product Column Name:")
            with col_b:
                category_column = st.selectbox("Category Column (Optional):", ["None"] + list(df.columns))
                stock_column = st.text_input("Enter stock column name:")
 
            st.divider()
            st.subheader("Lead Time Configuration")
            
            lt_method = st.radio(
                "How would you like to set lead times?",
                [
                    "Upload a lead time table (Product_ID → Lead_Time_Days)",
                    "Set by product category",
                    "Use one default for all products"
                ]
            )

            if lt_method == "Use one default for all products":
                default_lt = st.number_input("Default lead time (days):", min_value=1, value=3)
                df['Lead_Time'] = default_lt 
                
            elif lt_method == "Set by product category" and category_column != "None":
                st.write("Set lead times for your main categories below:")
                categories = df[category_column].dropna().unique()
                lead_times = {}
                cols = st.columns(3)
                for index, cat in enumerate(categories):
                    with cols[index % 3]:
                        lead_times[cat] = st.number_input(f"{cat} (days):", min_value=1, value=3, key=f"lt_{cat}")
                
                df['Lead_Time'] = df[category_column].map(lead_times).fillna(3)
                
            elif lt_method == "Upload a lead time table (Product_ID → Lead_Time_Days)":
                lt_file = st.file_uploader("Upload your Lead Time CSV (Must have a Product and Lead Time column)", type="csv")
                if lt_file:
                    lt_df = pd.read_csv(lt_file)
                    st.write("Map the columns from your uploaded lead time file:")
                    lt_col1, lt_col2 = st.columns(2)
                    with lt_col1:
                        lt_prod_col = st.selectbox("Product Name/ID Column:", lt_df.columns, key="lt_csv_prod")
                    with lt_col2:
                        lt_days_col = st.selectbox("Lead Time (Days) Column:", lt_df.columns, key="lt_csv_days")
                    
                    # Create a mapping dictionary and apply it to the main dataset
                    lt_dict = dict(zip(lt_df[lt_prod_col], lt_df[lt_days_col]))
                    df['Lead_Time'] = df[product_column].map(lt_dict).fillna(3) # Defaults to 3 if a product is missing from the upload
                    st.success("Lead times configured successfully!")
                else:
                    st.warning("Waiting for file upload... Products will default to 3 days.")
                    df['Lead_Time'] = 3
            else:
                df['Lead_Time'] = 3

            st.divider()

            st.divider()

            st.session_state['my_saved_df'] = df
            st.session_state['saved_sales_col'] = sales_column
            st.session_state['saved_product_col'] = product_column
            st.session_state['is_bulk'] = True

            if st.button("Run Bulk Analysis"):
                # Initialize class with the full dataframe and tell it which columns to use
                alert = StockAlert(
                    targeted_sales=df, 
                    sales_column=sales_column, 
                    product_column=product_column, 
                    inventory_column=stock_column,
                    lead_time=None # We handle lead time dynamically inside the class now
                )
                
                # FIXED: Actually calling the class method!
                results_df = alert.calculate_all_rops()
                alert.start_scheduler(review_period)
                st.write("### 3. Bulk Results")
                st.success("Backend automated analysis will appear here.")
                st.success(f"Scheduler activated: ROP will recalculate every {max(1, review_period // 7)} weeks.")

                filter_option = st.radio("Show:", ["All Products", "Needs Reorder Only", "OK Only"], horizontal=True)
                if filter_option == "Needs Reorder Only":
                    display_df = results_df[results_df["Status"] == "⚠️ REORDER"]
                elif filter_option == "OK Only":
                    display_df = results_df[results_df["Status"] == "✅ OK"]
                else:
                    display_df = results_df
                st.session_state['bulk_alert'] = alert
                if st.button("🔄 Refresh Bulk Stock Status"):
                    if 'bulk_alert' in st.session_state:
                        st.session_state['bulk_alert'].clean()
                        updated_results = st.session_state['bulk_alert'].calculate_all_rops()
                        st.dataframe(updated_results, use_container_width=True)
                        st.success("Stock status recalculated successfully!")
                    else:
                        st.warning("No data found to refresh. Please run an analysis first.")
    elif data_source == "Connect to Database":
        st.subheader("Connect to Database for Bulk Analysis")
        
        db_col1, db_col2 = st.columns(2)
        with db_col1:
            db_type = st.selectbox("Database Type:", ["mysql", "postgresql", "sqlite"])
            db_port = st.text_input("Port (e.g., 3306 or 5432):")
            db_pass = st.text_input("Password:", type="password")
            sales_table = st.text_input("Sales Table Name:")
        with db_col2:
            db_host = st.text_input("Host (e.g., localhost):")
            db_user = st.text_input("Username:")
            db_name = st.text_input("Database Name:")


        st.divider()
        st.write("### 1. Map Your Columns")
        # Note: We must use text inputs here because Streamlit hasn't queried the database yet to know the columns
        col_a, col_b = st.columns(2)
        with col_a:
            product_column = st.text_input("Product Column Name:")
            sales_column = st.text_input("Sales Column Name (e.g., Units Sold):")
            review_period = st.number_input("Review Period (Days):", value=90)
        with col_b:
            inventory_column = st.text_input("Inventory Column Name (for current stock):")
            category_column = st.text_input("Category Column (Optional - leave blank if none):")
            
        st.divider()
        st.subheader("2. Lead Time Configuration")
        
        lt_method = st.radio(
            "How would you like to set lead times?",
            [
                "Upload a lead time table (Product_ID → Lead_Time_Days)",
                "Use one default for all products"
            ]
        )
        
        # Setup variables before the button is clicked
        default_lt = 3
        lt_dict = {}
        
        if lt_method == "Use one default for all products":
            default_lt = st.number_input("Default lead time (days):", min_value=1, value=3)
            
        elif lt_method == "Upload a lead time table (Product_ID → Lead_Time_Days)":
            lt_file = st.file_uploader("Upload your Lead Time CSV", type="csv")
            if lt_file:
                lt_df = pd.read_csv(lt_file)
                st.write("Map the columns from your uploaded file:")
                lt_col1, lt_col2 = st.columns(2)
                with lt_col1:
                    lt_prod_col = st.selectbox("Product Name/ID Column:", lt_df.columns, key="lt_sql_prod")
                with lt_col2:
                    lt_days_col = st.selectbox("Lead Time (Days) Column:", lt_df.columns, key="lt_sql_days")
                
                lt_dict = dict(zip(lt_df[lt_prod_col], lt_df[lt_days_col]))



        if st.button("Connect & Run Bulk Analysis"):

            try:
                # Fetch the entire table by passing an empty string for product_name
                df = sql_connection(db_type, db_host, db_port, db_user, db_pass, db_name, sales_table, product_column, "")

                st.session_state['my_saved_df'] = df
                st.session_state['saved_sales_col'] = sales_column
                st.session_state['saved_product_col'] = product_column
                st.session_state['is_bulk'] = True 

                # Apply the correct lead time logic based on the user's choice
                if lt_method == "Use one default for all products":
                    df['Lead_Time'] = default_lt
                elif lt_method == "Upload a lead time table (Product_ID → Lead_Time_Days)":
                    df['Lead_Time'] = df[product_column].map(lt_dict).fillna(3)
                
                alert = StockAlert(
                    targeted_sales=df, 
                    sales_column=sales_column, 
                    product_column=product_column, 
                    inventory_column=inventory_column,
                    lead_time=None
                )
                
                results_df = alert.calculate_all_rops()
                alert.start_scheduler(review_period)
                
                st.write("### 3. Bulk Results")
                st.success(f"Scheduler activated: ROP will recalculate every {max(1, review_period // 7)} weeks.")

                filter_option = st.radio("Show:", ["All Products", "Needs Reorder Only", "OK Only"], horizontal=True)
                if filter_option == "Needs Reorder Only":
                    display_df = results_df[results_df["Status"] == "⚠️ REORDER"]
                elif filter_option == "OK Only":
                    display_df = results_df[results_df["Status"] == "✅ OK"]
                else:
                    display_df = results_df
                    
                st.dataframe(display_df, use_container_width=True)
                st.metric("Products Needing Urgent Reorder", len(results_df[results_df["Status"] == "⚠️ REORDER"]))
                
                st.session_state['bulk_alert_sql'] = alert

            except Exception as e:
                st.error(f"Error connecting to database or processing data: {e}")

        if st.button("🔄 Refresh Bulk Stock Status"):
            if 'bulk_alert_sql' in st.session_state:
                st.session_state['bulk_alert_sql'].clean()
                updated_results = st.session_state['bulk_alert_sql'].calculate_all_rops()
                st.dataframe(updated_results, use_container_width=True)
                st.success("Stock status recalculated successfully!")
            else:
                st.warning("No data found to refresh. Please run an analysis first.")

def render_auto_tab():
    st.header("Automatic ROP Calculation")
    analysis_scope = st.radio("What would you like to analyze?", ["Single Product", "All Products"])
    if analysis_scope == "Single Product":
        handle_single_product()
    else:
        handle_bulk_products()

def render_order_planner_tab():
    st.header("Order Quantity Planning")
    st.write("Plan your next purchase based on your calculated ROP and Average Sales.")

    col_x, col_y = st.columns(2)
    with col_x: known_rop = st.number_input("Calculated ROP:", min_value=0.0)
    with col_y: known_avg_sales = st.number_input("Average Daily Sales:", min_value=0.0)

    st.divider()
    calc_choice = st.radio("What would you like to calculate?", ["Days of Stock (I know the qty)", "Order Quantity (I know the days)"])

    if calc_choice == "Days of Stock (I know the qty)":
        qty = st.number_input("Desired order quantity (units):", min_value=0, step=1)
        if st.button("Calculate Days"):
            if known_avg_sales > 0:
                st.success(f"📦 {qty} units will last approximately **{(qty - known_rop) / known_avg_sales:.1f} days**.")
            else:
                st.warning("Average sales must be > 0.")
    else:
        days = st.number_input("Desired stock duration (days):", min_value=0, step=1)
        if st.button("Calculate Quantity"):
            st.success(f"🛒 Recommended order quantity for {days} days: **{known_rop + (known_avg_sales * days):.1f} units**.")

def render_forecast_tab():
    st.header("Seasonal Forecasting")
    st.write("Forecast future sales using Prophet with holiday effects.")
    
    col_start, col_end = st.columns(2)
    with col_start:
        start_date = st.date_input("Start Date")
        country = st.text_input("Enter country code for holidays (e.g., 'EG', 'US'):")
    with col_end:
        end_date = st.date_input("End Date")

    if st.button("Calculate Seasonal ROP"):
        # 1. Check if we have data saved in session state first
        if 'my_saved_df' not in st.session_state or 'saved_sales_col' not in st.session_state:
            st.warning("Please go to the Automatic Calculation tab and run an analysis first to load data.")
            return # Stop rendering the rest of the tab until data exists

        forecast_df = st.session_state['my_saved_df'].copy()
        
        # 2. If data came from Bulk Analysis, let the user pick a product
        if st.session_state.get('is_bulk'):
            prod_col = st.session_state['saved_product_col']
            selected_product = st.selectbox("Select a product to forecast:", forecast_df[prod_col].unique())
            
            # Filter the dataframe to just that product
            forecast_df = forecast_df[forecast_df[prod_col] == selected_product]
            
            # Extract that specific product's lead time from the column
            current_lead_time = forecast_df['Lead_Time'].iloc[0] if 'Lead_Time' in forecast_df.columns else 3
        else:
            # If it came from Single Product analysis
            selected_product = st.session_state.get('saved_product_name', 'Product')
            current_lead_time = st.session_state.get('saved_leadtime', 3)
        st.divider()
        m = Prophet() 
        if country: m.add_country_holidays(country_name=country)
        
        prophet_df = forecast_df.rename(columns={find_date_column(forecast_df): 'ds', st.session_state['saved_sales_col']: 'y'})
        m.fit(prophet_df)
        
        forecast = m.predict(m.make_future_dataframe(periods=365))
        mask = (forecast['ds'] >= pd.to_datetime(start_date)) & (forecast['ds'] <= pd.to_datetime(end_date))
        specific_period_data = forecast.loc[mask]

        if not specific_period_data.empty:
            seasonal_alert = StockAlert(targeted_sales=specific_period_data, sales_column='yhat', lead_time=current_lead_time)
            seasonal_rop, seasonal_avg, seasonal_std = seasonal_alert.calculate_rop()
            
            st.divider()
            st.write("### 📈 Forecasted Sales Trend")
            chart_data = specific_period_data[['ds', 'yhat']].rename(columns={'ds': 'Date', 'yhat': 'Forecasted Sales'}).set_index('Date')
            st.line_chart(chart_data)

            st.subheader("🎯 Projected Seasonal ROP")
            st.write(f"**Recommended Reorder Point:** {seasonal_rop:.1f} units")
            st.write(f"*(Forecasted Avg Daily Sales: {seasonal_avg:.1f} | Forecasted Std Dev: {seasonal_std:.1f})*")
        else:
            st.warning("No forecast data available for the selected dates.")
    else:
        st.warning("Please go to the Automatic Calculation tab and run single product analysis first to save data.")

# ==========================================
# 🚀 MAIN APP EXECUTION
# ==========================================

def main():
    st.set_page_config(page_title="StockAlert ROP Calculator", layout="wide")
    st.title("📦 StockAlert Inventory Manager")

    tab_manual, tab_auto, tab_order, tab_forcasting = st.tabs([
        "🧮 Manual ROP", "🤖 Automatic Calculation", "📦 Order Quantity Planner", "📊 Seasonal Forecasting"
    ])

    with tab_manual:
        render_manual_tab()
    
    with tab_auto:
        render_auto_tab()
        
    with tab_order:
        render_order_planner_tab()
        
    with tab_forcasting:
        render_forecast_tab()

if __name__ == "__main__":
    main()