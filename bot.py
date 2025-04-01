import telebot
import threading
import asyncio
import csv
import os
from tools_handler import calculate_quotation, generate_pdf_quote, save_sales, save_approved_quotation, Menu_item, Order
import tools_handler as tl
from agents import Agent, Runner, handoff, function_tool, RunContextWrapper
from dotenv import load_dotenv

from pydantic import BaseModel
from typing import Dict, Any, List, Optional, Union
from datetime import datetime

load_dotenv()
# Your Telegram Bot Token.
TELEGRAM_USERNAME="@leyla_cuisine_bot"
API_KEY = "7700372233:AAFVDBqM-t6PCVR3kXNiywyZR6V-WY5b640"
bot = telebot.TeleBot(API_KEY)




@bot.message_handler(commands=['Greet'])
def greet(message):
    bot.reply_to(message, "Hello! How can I assist you today?")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    threading.Thread(target=process_message, args=(message,)).start()

def update_contacts(name: str, email: str, phone_number: str = "", address: str = ""):
    """
    Append a new contact to contacts.csv if the email is not already present.
    Expected CSV columns: name, email, phone number, address.
    """
    filename = 'data/contacts.csv'
    fieldnames = ['name', 'email', 'phone number', 'address']
    try:
        contacts = []
        if os.path.exists(filename):
            with open(filename, newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile, fieldnames=fieldnames)
                for row in reader:
                    contacts.append(row)
        else:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
        exists = any(contact.get('email') == email for contact in contacts)
        if not exists:
            with open(filename, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writerow({'name': name, 'email': email, 'phone number': phone_number, 'address': address})
    except Exception as e:
        print("Error updating contacts:", e)

def confirmation_handler(message, pdf_path, recipient_email):
    text = message.text.strip().lower()
    if text.startswith("y"):
        from google_handlers.email_handler import send_quotation_email  # updated import path
        send_status = send_quotation_email(pdf_path, recipient_email=recipient_email)
        if send_status:
            bot.send_message(message.chat.id, "Quotation sent via email successfully!")
            saved_path = save_approved_quotation(pdf_path)
            bot.send_message(message.chat.id, f"Approved quotation saved as {saved_path}.")
        else:
            bot.send_message(message.chat.id, "Failed to send quotation via email.")
    else:
        bot.send_message(message.chat.id, "Quotation sending canceled. Please try again if needed.")

# Prepare the menu list for the parser instructions.
menu = tl.load_menu()
menu_items_str = '", "'.join(menu.keys())
menu_items_str = f'"{menu_items_str}"'
current_agent =''

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

# Create a new agent for menu operations with Menu_item as context.
menu_agent: Agent[Menu_item] = Agent[Menu_item](
    name="Menu agent",
    model='gpt-4o',
    instructions=(
        'You are a menu management agent that can add, edit, list, or delete menu items. '
        'When handling a menu operation, use the Menu_item structure for input. '
        'Output a message describing the operation performed. '
        f'Here is the current menu: {menu_items_str}.'
    ),
    tools=[tl.add_menu_item, tl.edit_menu_item, tl.delete_menu_item, tl.list_menu_items],
    output_type=Union[Menu_item, str],
)


# Handoff functions to update the current agent.
def on_handoff_menu(ctx: RunContextWrapper):
    global current_agent
    print("Handoff menu called")
    current_agent = 'Menu agent'
    print("Current agent set to:", current_agent)

def on_handoff_parser(ctx: RunContextWrapper):
    global current_agent
    print("Handoff parser called")
    current_agent = 'Parser agent'
    print("Current agent set to:", current_agent)



# Create triage_agent that chooses between order processing and menu operations.
triage_agent = Agent(
    name="Triage agent",
    model='gpt-4o',
    instructions=(
        'You are a triage agent that decides whether the user input is an order or a menu operation. Menu operations include keywords "menu", "add", "edit", or "delete"'
        ' For example, if the user input has an email in it or says "I want to order 6 hummus and 3 mansaf to vladimirabdelnour@gmail.com" then it is an order and should be handed to parser_agent. '
        'If the input is an order, return a JSON object matching the following structure: '
        '{"email": "customer@example.com", "items": [{"name": "Margherita Pizza", "quantity": 1}], "discount": "10%" or 10, "delivery": true, "tax_rate": 8.1} '
        'If the input is a menu operation hand off to the menu_agent'
    ),
    handoffs=[
        handoff(
            agent=parser_agent,
            on_handoff=on_handoff_parser
        ),
        handoff(
            agent=menu_agent,
            on_handoff=on_handoff_menu
        )
    ]
)


def process_message(message):
    print(f"Received message from {message.from_user.first_name}: {message.text}")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        bot.send_message(message.chat.id, "Processing your request, please wait...")
        # Use the triage agent to determine if the message is an order or a menu operation.
        result = loop.run_until_complete(Runner.run(triage_agent, message.text))
        
        # If the current agent is Menu agent, output the menu operation result.
        if current_agent == 'Menu agent':
            bot.send_message(message.chat.id, f"Menu operation result: {result.final_output}")
            return
        else:
            # Otherwise, process the order.
            bot.send_message(message.chat.id, "Processing order...")
            order = result.final_output
            print("Parsed Order:", order)
            
            if order.email:
                update_contacts(message.from_user.first_name, order.email)
            
            quotation = calculate_quotation(order)
            pdf_path = generate_pdf_quote(quotation)
            save_sales(quotation)
            
            summary = "Your order quotation is ready:\n\n"
            for item in quotation["quotation"]:
                summary += f"• {item['Item']} x{item['Quantity']} - ${item['Total Price']:.2f}\n"
            summary += f"\nGrand Total: ${quotation['final_total']:.2f}\n"
            summary += f"Send quotation to: {order.email if order.email else 'default@example.com'}\n"
            summary += "Confirm? [y/n]"
            
            bot.send_message(message.chat.id, summary)
            bot.register_next_step_handler(
                message, 
                lambda m: confirmation_handler(m, pdf_path, order.email if order.email else "default@example.com")
            )
            
    except Exception as e:
        bot.send_message(message.chat.id, f"Sorry, there was an error processing your request: {str(e)}")
        print(f"Error processing message: {str(e)}")


@bot.message_handler(commands=['Greet'])
def greet(message):
    bot.reply_to(message, "Hello! How can I assist you today?")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    threading.Thread(target=process_message, args=(message,)).start()

bot.polling()
