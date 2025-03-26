import telebot
import threading
import asyncio
import csv
import os
from tools import triage_agent, Runner, calculate_quotation, generate_pdf_quote, Order, save_sales, save_approved_quotation

# Your Telegram Bot Token.
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
    filename = 'contacts.csv'
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
        from email_handler import send_quotation_email
        send_status = send_quotation_email(pdf_path, recipient_email=recipient_email)
        if send_status:
            bot.send_message(message.chat.id, "Quotation sent via email successfully!")
            saved_path = save_approved_quotation(pdf_path)
            bot.send_message(message.chat.id, f"Approved quotation saved as {saved_path}.")
        else:
            bot.send_message(message.chat.id, "Failed to send quotation via email.")
    else:
        bot.send_message(message.chat.id, "Quotation sending canceled. Please try again if needed.")

def process_message(message):
    print(f"Received message from {message.from_user.first_name}: {message.text}")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        bot.send_message(message.chat.id, "Processing your request, please wait...")
        # Use triage_agent to decide if this is an order or a menu operation.
        result = loop.run_until_complete(Runner.run(triage_agent, message.text))
        
        print("Triage result:", result.final_output)

        # Check if the result came from the order parser (an Order instance)
        if "handing off to parser" in result.final_output:

            handoff_type = "order"  # processing order
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
                lambda m: confirmation_handler(
                    m,
                    pdf_path,
                    order.email if order.email else "default@example.com"
                )
            )
        else:
            handoff_type = "menu"  # menu operation
            bot.send_message(message.chat.id, f"Menu operation result: {result.final_output}")
            
        print("Handoff type:", handoff_type)
            
    except Exception as e:
        bot.send_message(message.chat.id, f"Sorry, there was an error processing your request: {str(e)}")
        print(f"Error processing message: {str(e)}")

bot.polling()
