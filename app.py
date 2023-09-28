import telebot
import random
import json
import functools as ft
import pandas as pd
import numpy as np
from math import radians, cos, sin, asin, sqrt
# from onemapsg import OneMapClient
from telebot import types
from typing import Final

CONFIG = json.load(open('./config.json'))

BOT_TOKEN: Final = CONFIG['BOT_TOKEN']
BOT_USERNAME: Final = CONFIG['BOT_USERNAME']
URL: Final = CONFIG['BOT_URL']
IMAGE_PATH = CONFIG['IMAGE_PATH_DEPLOY']

bot = telebot.TeleBot(BOT_TOKEN)

def calculate_distance(x):
    (lat1, lon1) = (1.28959031017024, 103.786921106765); (lat2, lon2) = (x['Latitude'], x['Longitude'])
    dlon = radians(lon2) - radians(lon1)
    dlat = radians(lat2) - radians(lat1)
    a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
    c = 2 * asin(sqrt(a))
    r = 6371
    return np.round((c * r), 2)

def travel_distance(x):
    if x['Time'] < 5:
        val = 'Near'
    elif x['Time'] > 10:
        val = 'Far'
    else:
        val = 'Middle'
    return val

distance_df = pd.read_csv('./distance.csv')
distance_df['Distance'] = distance_df.apply(lambda x: calculate_distance(x), axis=1)
distance_df['Time'] = distance_df['Distance'] / 4 * 60
distance_df['Travel'] = distance_df.apply(lambda x: travel_distance(x), axis=1)

shop_df = pd.read_csv('./shop.csv')

dfs = [distance_df, shop_df]
df_final = ft.reduce(lambda left, right: pd.merge(left, right, on='Index'), dfs)

@bot.message_handler(commands=['help', 'start'])
def start(message):
    bot.reply_to(message, "Hello! Welcome to DSO Eats!\n/begin - start making your lunch plans\n/decide - generate a random location near DSO\n/donate - show some love :D")

user = {}

# Callback handler 1: Distance Preference
@bot.message_handler(commands=['begin'])
def begin(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user[chat_id] = {'Chat_Id': chat_id, 
                     'Travel':None, 
                     'Price':None, 
                     'Cuisine':None, 
                     'Recommendation':None, 
                     'State': 'begin'
                    }
    print(user)
    markup = types.InlineKeyboardMarkup()
    item1 = types.InlineKeyboardButton("Near", callback_data='Near')
    item2 = types.InlineKeyboardButton("Middle", callback_data='Middle')
    item3 = types.InlineKeyboardButton("Far", callback_data='Far')
    markup.add(item1, item2, item3)
    bot.send_message(chat_id, "How far are you willing to walk?\nNear - 5 mins\nMiddle - 10 mins\nFar - 15 mins", reply_markup=markup)
    user[user_id]['State'] = 'travel_selected'

# Callback handler 2: Price Preference
@bot.callback_query_handler(func=lambda call: call.data in ['Near', 'Middle', 'Far'])
def handle_callback_1(call):
    user_id = call.message.from_user.id
    chat_id = call.message.chat.id
    user[chat_id]['Travel'] = call.data
    print(user)
    markup = types.InlineKeyboardMarkup()
    item1 = types.InlineKeyboardButton("Cheap", callback_data='Cheap')
    item2 = types.InlineKeyboardButton("Affordable", callback_data='Affordable')
    item3 = types.InlineKeyboardButton("Expensive", callback_data='Expensive')
    markup.add(item1, item2, item3)
    if user[chat_id]['State'] == 'travel_selected': 
        bot.send_message(chat_id, "How much are you willing to spend?\nCheap - < 5 dollars\nAffordable - < 10 dollars\nExpensive - < 15 dollars", reply_markup=markup)
        user[chat_id]['State'] = 'price_selected'

# Callback handler 3: Cuisine Preference
@bot.callback_query_handler(func=lambda call: call.data in ['Cheap', 'Affordable', 'Expensive'])
def handle_callback_2(call):
    user_id = call.message.from_user.id
    chat_id = call.message.chat.id
    user[chat_id]['Price'] = call.data
    print(user)
    markup = types.InlineKeyboardMarkup()
    items = []
    for cuisine in shop_df['Cuisine'].unique():
        items.append(types.InlineKeyboardButton(cuisine, callback_data=cuisine))
    markup.add(*items)
    if user[chat_id]['State'] == 'price_selected':
        bot.send_message(chat_id, "What cuisine are you feeling?", reply_markup=markup)
        user[chat_id]['State'] = 'cuisine_selected'

# Callback handler 4: Make Recommendation
@bot.callback_query_handler(func=lambda call: call.data in shop_df['Cuisine'].unique())
def handle_callback_3(call):
    user_id = call.message.from_user.id
    chat_id = call.message.chat.id
    user[chat_id]['Cuisine'] = call.data
    print(user)
    interim1 = df_final[df_final['Travel'] == user[chat_id]['Travel']]
    interim2 = interim1[interim1['Price'] == user[chat_id]['Price']]
    interim3 = interim2[interim2['Cuisine'] == user[chat_id]['Cuisine']]
    
    if user[chat_id]['State'] == 'ended':
        pass
    
    elif user[chat_id]['State'] == 'cuisine_selected' and not interim3.empty:
        interim4 = interim3.reset_index(drop=True)
        random_choice = random.randint(0, len(interim4)-1)
        selection = interim4.iloc[random_choice]
        place = selection['Name']; shop = selection['Shop']
        user[chat_id]['Recommendation'] = (interim4, [random_choice])
        bot.send_message(chat_id, f"{place} - {shop}\n\nDissatisfied with the recommendation?\nGet another recommendation /reroll\nTry again /begin")

    else:
        bot.send_message(chat_id, f"There is no available option - Please try again! /begin")
    
    user[chat_id]['State'] = 'ended'
    print(user)

@bot.message_handler(commands=['reroll'])
def reroll(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    try:
        user_selections = user[chat_id]
    except:
        return
    if user_selections['State'] != 'ended' or user_selections['Recommendation'] == None:
        print(f'User {chat_id} attempted to reroll without any recommendations')
        pass
    else:
        df_ref, recommended_index = user_selections['Recommendation']
        all_index = [i for i in range(0, len(df_ref))]
        new_index = list(set(all_index) ^ set(recommended_index))
        if not new_index:
            bot.send_message(chat_id, f"There is no available option - Please try again! /begin")
        else:
            random_choice = random.choice(new_index)
            recommended_index.append(random_choice)
            selection = df_ref.iloc[random_choice]
            place = selection['Name']; shop = selection['Shop']
            user[chat_id]['Recommendation'] = (df_ref, recommended_index)
            bot.send_message(chat_id, f"{place} - {shop}\n\nDissatisfied with the recommendation?\nGet another recommendation /reroll\nTry again /begin")
    print(user)

@bot.message_handler(commands=['decide'])
def decide(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    num_choices = len(df_final)
    choice_num = np.random.choice(np.arange(1, num_choices+1), p=[1/num_choices] * num_choices) - 1
    place = df_final.iloc[choice_num]['Name']; shop = df_final.iloc[choice_num]['Shop']
    bot.reply_to(message, f'{place} - {shop}')

@bot.message_handler(commands=['donate'])
def donate(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    with open(IMAGE_PATH, 'rb') as photo:
        bot.send_photo(chat_id, photo)

if __name__ == '__main__':
    print('starting up bot...')
    bot.polling()