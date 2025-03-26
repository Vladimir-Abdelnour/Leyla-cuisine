import csv
import difflib
import asyncio
import os
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from enum import Enum

from pydantic import BaseModel
from agents import Agent, Runner, handoff, function_tool, RunContextWrapper
from fpdf import FPDF  # Install via: pip install fpdf

MENU_CSV_PATH = "menu.csv"

# Extended Order models (added email and tax_rate)
class OrderItem(BaseModel):
    name: str
    quantity: int

class Order(BaseModel):
    email: Optional[str]  # Customer email.
    items: List[OrderItem]
    discount: Optional[Union[str, float]]
    delivery: Optional[bool]
    tax_rate: Optional[float] = None  # Tax rate if specified.

# Enum for menu categories
class CategoryEnum(str, Enum):
    appetizers = "appetizers"
    salad = "salad"
    main_dish = "main dish"
    deserts = "deserts"

class Menu_item(BaseModel):
    Item: str
    Price: float  
    Category: CategoryEnum
    Description: Optional[str] = None

def load_menu(csv_path: str = MENU_CSV_PATH) -> Dict[str, Dict[str, Any]]:
    """
    Load the menu from a CSV file.
    Expected CSV columns: Item, Price, Category, Description.
    """
    menu = {}
    with open(csv_path, newline='', encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            row['Price'] = float(row['Price'])
            menu[row['Item']] = row
    return menu

def calculate_quotation(order: Order) -> Dict[str, Any]:
    """
    Calculate a quotation using the order information.
    Uses order.tax_rate if provided; otherwise defaults to 8.1%.
    Each order line now also includes the item’s category.
    """
    menu = load_menu()
    quotation_lines = []
    subtotal = 0.0

    for order_item in order.items:
        ordered_item = order_item.name
        qty = order_item.quantity

        if ordered_item in menu:
            menu_item = menu[ordered_item]
        else:
            matches = difflib.get_close_matches(ordered_item, menu.keys(), n=1, cutoff=0.6)
            if matches:
                menu_item = menu[matches[0]]
            else:
                raise ValueError(f"Item '{ordered_item}' not found in menu.")

        unit_price = menu_item['Price']
        total_price = unit_price * qty
        subtotal += total_price

        quotation_lines.append({
            "Item": menu_item['Item'],
            "Quantity": qty,
            "Unit Price": unit_price,
            "Total Price": total_price,
            "Category": menu_item.get('Category', 'Uncategorized')
        })

    discount_value = 0.0
    if order.discount is not None:
        if isinstance(order.discount, str) and order.discount.strip().endswith("%"):
            try:
                discount_percentage = float(order.discount.strip().strip("%"))
                discount_value = subtotal * (discount_percentage / 100)
            except ValueError:
                discount_value = 0.0
        else:
            try:
                discount_value = float(order.discount)
            except ValueError:
                discount_value = 0.0

    adjusted_total = subtotal - discount_value
    if order.tax_rate is not None:
        tax = adjusted_total * (order.tax_rate / 100)
    else:
        tax = adjusted_total * 0.081
    delivery_fee = 15 if order.delivery else 0
    final_total = adjusted_total + tax + delivery_fee

    return {
        "quotation": quotation_lines,
        "subtotal": subtotal,
        "discount": discount_value,
        "tax": tax,
        "delivery_fee": delivery_fee,
        "final_total": final_total
    }

def generate_pdf_quote(quotation: Dict[str, Any], output_path: str = "quotation.pdf") -> str:
    """
    Generate a PDF quotation that groups items by category.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_fill_color(240, 248, 255)
    pdf.rect(0, 0, 210, 50, 'F')

    try:
        pdf.image("logo.png", x=10, y=8, w=30)
    except RuntimeError:
        pass

    pdf.set_xy(0, 20)
    pdf.set_font("Arial", "B", 24)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, "Quotation", ln=True, align="C")
    pdf.ln(10)
    pdf.set_font("Arial", "", 12)
    current_date = datetime.now().strftime("%Y-%m-%d")
    pdf.cell(0, 10, f"Date: {current_date}", ln=True, align="R")
    pdf.cell(0, 10, "ABC Restaurant", ln=True, align="C")
    pdf.cell(0, 10, "123 Main St, City, Country", ln=True, align="C")
    pdf.cell(0, 10, "Phone: (123) 456-7890 | Email: info@abcrestaurant.com", ln=True, align="C")
    pdf.ln(5)

    grouped = {}
    for line in quotation["quotation"]:
        cat = line["Category"]
        grouped.setdefault(cat, []).append(line)

    for category, items in grouped.items():
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, category, ln=True)
        pdf.ln(2)
        headers = ["Item", "Quantity", "Unit Price", "Total Price"]
        col_widths = [60, 30, 30, 30]
        pdf.set_font("Arial", "B", 12)
        pdf.set_fill_color(200, 200, 200)
        pdf.set_text_color(0, 0, 0)
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 10, header, border=1, align="C", fill=True)
        pdf.ln()
        pdf.set_font("Arial", "", 12)
        for item in items:
            pdf.cell(col_widths[0], 10, str(item["Item"]), border=1)
            pdf.cell(col_widths[1], 10, str(item["Quantity"]), border=1, align="C")
            pdf.cell(col_widths[2], 10, f"${item['Unit Price']:.2f}", border=1, align="R")
            pdf.cell(col_widths[3], 10, f"${item['Total Price']:.2f}", border=1, align="R")
            pdf.ln()
        pdf.ln(5)

    right_x = sum([60, 30, 30])
    pdf.set_font("Arial", "B", 12)
    pdf.cell(right_x, 10, "Subtotal", border=1)
    pdf.cell(30, 10, f"${quotation['subtotal']:.2f}", border=1, align="R")
    pdf.ln()
    pdf.cell(right_x, 10, "Discount", border=1)
    pdf.cell(30, 10, f"-${quotation['discount']:.2f}", border=1, align="R")
    pdf.ln()
    pdf.cell(right_x, 10, "Tax", border=1)
    pdf.cell(30, 10, f"${quotation['tax']:.2f}", border=1, align="R")
    pdf.ln()
    pdf.cell(right_x, 10, "Delivery Fee", border=1)
    pdf.cell(30, 10, f"${quotation['delivery_fee']:.2f}", border=1, align="R")
    pdf.ln()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(right_x, 10, "Final Total", border=1, fill=True)
    pdf.cell(30, 10, f"${quotation['final_total']:.2f}", border=1, align="R", fill=True)
    pdf.ln(15)
    pdf.set_font("Arial", "I", 12)
    pdf.cell(0, 10, "Thank you for your business!", ln=True, align="C")

    pdf.output(output_path)
    return output_path

def save_sales(quotation: Dict[str, Any]):
    """
    Save the sales for the current month to sales.csv.
    For each item, record: Date, Month, Item, Quantity, Total Sales.
    """
    filename = 'sales.csv'
    fieldnames = ['Date', 'Month', 'Item', 'Quantity', 'Total Sales']
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    current_month = now.strftime("%Y-%m")
    try:
        file_exists = os.path.exists(filename)
        with open(filename, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            for line in quotation["quotation"]:
                writer.writerow({
                    'Date': current_date,
                    'Month': current_month,
                    'Item': line['Item'],
                    'Quantity': line['Quantity'],
                    'Total Sales': line['Total Price']
                })
    except Exception as e:
        print("Error saving sales data:", e)

def save_approved_quotation(pdf_path: str) -> str:
    """
    Save the approved quotation PDF to the 'Approved Quotations' folder with file name Quote_YYYYMMDD.pdf.
    Returns the new file path.
    """
    folder = "Approved Quotations"
    if not os.path.exists(folder):
        os.makedirs(folder)
    date_str = datetime.now().strftime("%Y%m%d")
    new_filename = f"Quote_{date_str}.pdf"
    new_path = os.path.join(folder, new_filename)
    try:
        with open(pdf_path, 'rb') as src, open(new_path, 'wb') as dst:
            dst.write(src.read())
        return new_path
    except Exception as e:
        print("Error saving approved quotation:", e)
        return pdf_path

# Prepare the menu list for the parser instructions.
menu = load_menu()
menu_items_str = '", "'.join(menu.keys())
menu_items_str = f'"{menu_items_str}"'


# Updated parser_agent that now expects email and optionally a tax_rate.
parser_agent = Agent(
    name='order_parser',
    model='gpt-4o',
    instructions=(
        'You are a helpful assistant that parses the user input and returns a JSON object matching the following structure: '
        '{"email": "customer@example.com", "items": [{"name": "Margherita Pizza", "quantity": 1}], "discount": "10%" or 10, "delivery": true, "tax_rate": 8.1} '
        'Your output should exactly match the naming of the food in the CSV. '
        f'Here is the menu list: {menu_items_str}. '
        'Note: The user may provide a discount as a percentage (e.g., "10%") or as a flat number (e.g., 10), '
        'indicate delivery by specifying "delivery": true or false, include their email address, '
        'and optionally specify a tax rate as a number (e.g., 8.1 for 8.1%).'
    ),
    output_type=Order,
)

@function_tool
async def add_menu_item(wrapper: RunContextWrapper[Menu_item], menu_item: Menu_item) -> str:
    """Adds a new menu item to the menu CSV file using Menu_item format."""
    fieldnames = ['Item', 'Price', 'Category', 'Description']
    try:
        file_exists = os.path.exists(MENU_CSV_PATH)
        with open(MENU_CSV_PATH, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow({
                'Item': menu_item.Item,
                'Price': menu_item.Price,
                'Category': menu_item.Category,
                'Description': menu_item.Description or ""
            })
        return f"Added menu item: {menu_item.Item} in category {menu_item.Category} at price {menu_item.Price}."
    except Exception as e:
        return f"Error adding menu item: {str(e)}"

@function_tool
async def edit_menu_item(wrapper: RunContextWrapper[Menu_item], menu_item: Menu_item) -> str:
    """Edits an existing menu item in the menu CSV file using Menu_item format."""
    fieldnames = ['Item', 'Price', 'Category', 'Description']
    try:
        updated = False
        rows = []
        with open(MENU_CSV_PATH, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row['Item'] == menu_item.Item:
                    row['Price'] = menu_item.Price
                    row['Category'] = menu_item.Category
                    row['Description'] = menu_item.Description or ""
                    updated = True
                rows.append(row)
        if not updated:
            return f"Menu item '{menu_item.Item}' not found for editing."
        with open(MENU_CSV_PATH, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return f"Edited menu item: {menu_item.Item}. Updated category to {menu_item.Category}, price to {menu_item.Price}."
    except Exception as e:
        return f"Error editing menu item: {str(e)}"

@function_tool
async def delete_menu_item(wrapper: RunContextWrapper[Menu_item], menu_item: Menu_item) -> str:
    """Deletes an existing menu item from the menu CSV file using Menu_item format."""
    fieldnames = ['Item', 'Price', 'Category', 'Description']
    try:
        deleted = False
        rows = []
        with open(MENU_CSV_PATH, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row['Item'] == menu_item.Item:
                    deleted = True
                    continue
                rows.append(row)
        if not deleted:
            return f"Menu item '{menu_item.Item}' not found for deletion."
        with open(MENU_CSV_PATH, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return f"Deleted menu item: {menu_item.Item}."
    except Exception as e:
        return f"Error deleting menu item: {str(e)}"


# Create a new agent for menu operations with Menu_item as context.
menu_agent: Agent[Menu_item] = Agent[Menu_item](
    name="Menu agent",
    model='gpt-4o',
    instructions=(
        'You are a menu management agent that can add, edit, or delete menu items. '
        'When handling a menu operation, use the Menu_item structure for input. '
        'Output a message describing the operation performed. '
        f'Here is the current menu: {menu_items_str}.'
    ),
    tools=[add_menu_item, edit_menu_item, delete_menu_item],
    output_type=Union[Menu_item, str],
)


# Define on_handoff callbacks that log which agent is being handed off to.
def on_handoff_order(ctx):
    print("Handoff made to order_parser.")

def on_handoff_menu(ctx):
    print("Handoff made to Menu agent.")

# Create handoff objects with custom tool names and callbacks.
parser_handoff = handoff(
    agent=parser_agent,
    tool_name_override="handoff_to_order_parser",
    on_handoff=on_handoff_order,
)

menu_handoff = handoff(
    agent=menu_agent,
    tool_name_override="handoff_to_menu_agent",
    on_handoff=on_handoff_menu,
)





# Create triage_agent that chooses between order processing and menu operations.
triage_agent = Agent(
    name="Triage agent",
    instructions=(
        'You are a triage agent that decides whether the user input is an order or a menu operation. Menu operations include keywords "menu", "add", "edit", or "delete"'
        ' For example, if the user input has an email in it or says "I want to order 6 hummus and 3 mansaf to vladimirabdelnour@gmail.com" then it is an order and should be handed to parser_agent. '
        'If the input is an order, output "handing off to parser" and return an Order JSON object using order_parser instructions. '
        'If the input is a menu operation hand off to the menu_agent and return its message.'
    ),
    handoffs=[parser_agent, menu_agent],
)

async def main():
    # Example bot input; adjust this value to simulate different user requests.
    bot_input = "I would like to add a new menu item for Caesar Salad."
    
    # Run the triage_agent. Its output will come either from the parser_agent or the menu_agent.
    result = await Runner.run(triage_agent, bot_input)
    final_output = result.final_output
    
    # Determine handoff type based on the output.
    # We expect an Order object for an order handoff (via parser_agent)
    # and a string or Menu_item for a menu operation (via menu_agent).
    if isinstance(final_output, Order):
        handoff_type = "order"
        order = final_output
        print("Parsed Order:", order)
        quotation = calculate_quotation(order)
        pdf_path = generate_pdf_quote(quotation)
        print(f"Quotation generated at: {pdf_path}")
    else:
        handoff_type = "Menu"
        print("Menu operation output:", final_output)
    
    print("Handoff type:", handoff_type)

if __name__ == "__main__":
    asyncio.run(main())
