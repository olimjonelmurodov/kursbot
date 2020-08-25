#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging, base64, json, config, psycopg2, re, threading, ssl, math
import urllib.request
from bs4 import BeautifulSoup
from decimal import Decimal
from io import BytesIO
from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, ParseMode
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, Defaults,
                          ConversationHandler, CallbackQueryHandler)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

LANGUAGE_CHOICE, PHONE_CHOICE, NAME_CHOICE, MAIN_CHOICE, TRANSFER_CHOICE, \
TO_CHINA_AMOUNT, TO_CHINA_CARD, \
TO_CHINA_CURRENCY, PAY_TO_CONFIRMATION_CHOICE, PAY_TO_METHOD_CHOICE, PAY_TO_WAIT_CHOICE, PAY_TO_RECEIVE_CARD_TYPE, PAY_TO_RECEIVE_CARD_NUMBER, \
FROM_CHINA_CURRENCY, FROM_CHINA_AMOUNT, \
PAY_METHOD_CHOICE, PAY_WAIT_CHOICE, PAY_CONFIRMATION_CHOICE, PAY_RECEIVE_CARD_TYPE, PAY_RECEIVE_CARD_NUMBER, \
HISTORY, RECEIVE_CONFIRMATION_IMAGE, RECEIVE_CONFIRMATION_CARD = range(23)
db = psycopg2.connect(**config.dbcfg)
cursor = db.cursor()

def printnum(val):
    val = remove_exponent(str(val))
    return '{:,}'.format(val).replace(',', ' ')

def remove_exponent(val):
    d=Decimal(val)
    if d:
        return d.quantize(Decimal(1)) if d == d.to_integral() else d.normalize()
    else:
        return None

def get_uzs_rate():
    myssl = ssl.create_default_context();
    myssl.check_hostname=False
    myssl.verify_mode=ssl.CERT_NONE
    with urllib.request.urlopen("https://nbu.uz/en/exchange-rates/json/", context = myssl) as url:
        data = json.loads(url.read().decode())
        for i in data:
            if i['code']=='USD':   
                return (float(i['nbu_cell_price'])*100, float(i['nbu_buy_price'])*100)

def get_cny_rate():
    contents = urllib.request.urlopen("https://www.boc.cn/sourcedb/whpj/enindex_1619.html").read()
    html_soup = BeautifulSoup(contents, "html.parser")
    squery = html_soup.findAll('td', attrs = {'bgcolor':'#FFFFFF'}) 
    for i in range(len(squery)):
        if "USD" in squery[i]:
            return (float(striptags(squery[i+4]))*100, float(striptags(squery[i+5]))*100)
            print("Cash selling rate:", striptags(squery[i+4]))
            print("Middle rate:", striptags(squery[i+5]))


def striptags(s):
    return re.sub('<[^<]+?>', '', str(s))

def update_currency_regularly():
    threading.Timer(86400.0, update_currency_regularly).start()
    sql = "INSERT INTO currency_rates (currency_value, sell_rate, buy_rate) VALUES ('UZS', %s, %s)"
    data = get_uzs_rate()
    if data:
        cursor.execute(sql, data)
        db.commit()
    sql = "INSERT INTO currency_rates (currency_value, sell_rate, buy_rate) VALUES ('CNY', %s, %s)"
    data = get_cny_rate()    
    if data:
        cursor.execute(sql, data)
        db.commit()

def get_uzs():
    sql = "SELECT sell_rate, buy_rate from currency_rates WHERE currency_value='UZS' order by id desc limit 1;"
    cursor.execute(sql)
    res=cursor.fetchone()
    return (int(res[0])/100, int(res[1])/100)

def get_cny():
    sql = "SELECT sell_rate, buy_rate from currency_rates WHERE currency_value='CNY' order by id desc limit 1;"
    cursor.execute(sql)
    res=cursor.fetchone()
    return (int(res[0])/100, int(res[1])/100)

def regex_prepare(s):
    return '^'+re.escape(s)+'$'

def do_nothing(update, context):
    pass

def truz(s):
    for word in words:
        if word[1]==s:
            return word[2]
    return s.replace('_', ' ').title()

def trru(s):
    for word in words:
        if word[1]==s:
            return word[3]
    return s.replace('_', ' ').title()

def tr(s, context):
    if russian(context):
        return trru(s)
    elif uzbek(context):
        return truz(s)
    else: 
        return truz(s)

def vtr(s, context):
    if russian(context):
        sql = "SELECT russian FROM vwords where keyword=%s"
    else: 
        sql = "SELECT uzbek FROM vwords where keyword=%s"
    data=(s,)
    res = db_execute(sql, data)
    if res:
        return res[0][0]
    else:
        return s.replace('_', ' ').title()

defaults = Defaults(parse_mode=ParseMode.HTML)

def uzbek(context):
    if context.user_data['lang']==0:
        return True
    return False

def russian(context):
    if context.user_data['lang']==1:
        return True
    return False
        
def db_execute(sql, data = None, commit=False):
        if data is None:
            cursor.execute(sql)
        else:
            cursor.execute(sql, data)
        if commit:
            db.commit()
            return True
        res = cursor.fetchall()
        return res

sql = "SELECT * from words"
words = db_execute(sql)


def echo(update, context):
    conv_handler.handle_update(update, dp, ((update.message.from_user.id, update.message.from_user.id), MessageHandler(Filters.text, start), None), context)
    
def start(update, context):
    keyboard = [[truz('lang')],[trru('lang')]]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,  resize_keyboard=True)
    update.message.reply_text('Tilni tanlang/Выберите язык:', reply_markup=markup)
    return LANGUAGE_CHOICE

def uzbek_choice(update, context):
    context.user_data['lang']=0
    return request_phone(update, context)

def russian_choice(update, context):
    context.user_data['lang']=1
    return request_phone(update, context)

def request_phone(update, context):
    reply_markup = ReplyKeyboardMarkup([[KeyboardButton('📱 Raqamni kiritish', request_contact=True)]],  resize_keyboard=True)
    update.message.reply_text('"Raqamni kiritish" tugmasini bosing yoki qo\'lda kiriting (+998XXYYYYYYY shaklida).', reply_markup=reply_markup)
    return PHONE_CHOICE

def phone_auto(update, context):
    context.user_data['phone']=update.message.contact.phone_number
    return save_init_data(update, context)

def phone_manual(update, context):
    context.user_data['phone']=update.message.text
    return save_init_data(update, context)

def save_init_data(update, context):
    sql = "INSERT INTO users (name, phone, userid) SELECT %s, %s, %s WHERE NOT EXISTS(SELECT userid FROM users WHERE userid = %s)"
    data = (update.message.from_user.full_name, context.user_data['phone'], update.message.from_user.id, update.message.from_user.id)
    cursor.execute(sql, data)
    db.commit()
    return main_choice(update, context)

def main_choice(update, context):
    clear_context(context)
    keyboard = [[tr('transfer_money', context), tr('history', context)], [tr('rules_and_tariffs', context), tr('how_to_send', context)], [tr('receive_confirmation', context), tr('our_contacts', context)],[tr('back', context)]]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,  resize_keyboard=True)
    update.message.reply_text(tr('how_to_help', context), reply_markup=markup)
    return MAIN_CHOICE

def transfer_choice(update, context):
    keyboard = [[tr('to_china', context), tr('from_china', context)],[tr('back', context)]]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,  resize_keyboard=True)
    update.message.reply_text(tr('transfer', context), reply_markup=markup)
    return TRANSFER_CHOICE

def request_to_china_currency(update, context):
    keyboard=[]
    keyboard.append(['CNY', 'UZS'])
    keyboard.append([tr('back', context)])
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,  resize_keyboard=True)
    update.message.reply_text(tr('currency_to_receive', context), reply_markup=markup)
    return TO_CHINA_CURRENCY
    
def save_to_china_currency(update, context):
    context.user_data['currency']=update.message.text
    return request_to_china_amount(update, context)

def request_to_china_amount(update, context):
    keyboard = [[tr('back', context)]]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,  resize_keyboard=True)
    update.message.reply_text(tr('amount_to_send', context), reply_markup=markup)
    return TO_CHINA_AMOUNT

def save_to_china_amount(update, context):
    amount = int(update.message.text)*100
    if context.user_data['currency']=="UZS":
        uzs = int(get_uzs()[1])
        cny=int(get_cny()[0])/100.0
        delta = amount/uzs
        sql = "SELECT min_point, max_point, uzs_rate, cny_rate from tariff_rates where %s>min_point AND %s<=max_point;"
        data=(delta, delta)
        cursor.execute(sql, data)
        res = cursor.fetchone()
        if res:
            context.user_data['amount']=amount
            s="Komissiya: "+ printnum(res[2]/100.0) + ' so\'m'
            s+='\n'
            s+="Qabul qilinadi: (" + printnum(amount/100.0)+' - '+printnum(int(res[2])/100.0)+') / '+printnum(uzs)+' x ' +printnum(cny)+' = '+printnum(math.ceil((amount-res[2])/float(uzs)*cny/100.0)) + " yuan"
            s+='\n'
            context.user_data['fee'] = amount/100.0
            s+="Jo'natiladi: "+ printnum(context.user_data['fee']) + ' so\'m'
#            s+="Jo'natiladi: (" + printnum(amount/100.0)+' + '+printnum(int(res[2])/100.0)+') / '+printnum(uzs)+' x ' +printnum(cny)+' = '+ printnum(int(((amount-int(res[2]))/float(uzs))*cny/100.0)) + " yuan"
            update.message.reply_text(s)
        return request_pay_method(update, context)
    if context.user_data['currency']=="CNY":
        uzs = int(get_uzs()[1])
        cny=int(get_cny()[0])/100.0
        delta = amount/cny
        sql = "SELECT min_point, max_point, uzs_rate, cny_rate from tariff_rates where %s>min_point AND %s<=max_point;"
        data=(delta, delta)
        cursor.execute(sql, data)
        res = cursor.fetchone()
        if res:
            context.user_data['amount']=amount
            s="Komissiya: "+ printnum(res[2]/100.0) + ' so\'m'
            s+='\n'
            s+="Qabul qilinadi: "+ printnum(amount/100.0) + ' yuan'
            s+='\n'
            context.user_data['fee'] = math.ceil(((amount)/float(cny))*uzs/100.0)+int(res[2]/100.0)
            s+="Jo'natiladi: " + printnum(amount/100.0)+' / '+printnum(cny)+' x ' +printnum(uzs)+' + '+printnum(int(res[2])/100.0)+' = ' + printnum(context.user_data['fee']) + " so'm"
            update.message.reply_text(s)
        return request_to_pay_method(update, context)

def request_to_pay_method(update, context):
    keyboard=[]
    keyboard.append(['UzCard', 'HUMO'])
    keyboard.append([tr('back', context)])
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,  resize_keyboard=True)
    update.message.reply_text("Karta turini tanlang:", reply_markup=markup)
    return PAY_TO_METHOD_CHOICE

def save_to_pay_method(update, context):
    context.user_data['pay_method']=update.message.text
    if update.message.text=="HUMO":
        s = "HUMO: 0000 0000 0000 0000.\nShu raqamga {} so'm o'tkazing va davom etish tugmasini bosing.".format(printnum(context.user_data['fee']))
    else:
        s = "UZCARD: 0000 0000 0000 0000.\nShu raqamga {} so'm o'tkazing va davom etish tugmasini bosing.".format(printnum(context.user_data['fee']))
    return pay_to_wait(update, context, s)    

def pay_to_wait(update, context, s):
    keyboard=[]
    keyboard.append(['Davom etish'])
    keyboard.append([tr('back', context)])
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,  resize_keyboard=True)
    update.message.reply_text(s, reply_markup=markup)
    return PAY_TO_WAIT_CHOICE

def to_payment_confirmation(update, context):
    update.message.reply_text("To'lovni amalga oshirgandan keyin keladigan tranzaksiyaning oxirgi 5ta raqamini kiriting:")
    return PAY_TO_CONFIRMATION_CHOICE

def to_confirm_payment(update, context):
    context.user_data['last_digits']=update.message.text
    return request_to_receive_card_type(update, context)

def request_to_receive_card_type(update, context):
    keyboard=[]
    keyboard.append(['Alipay', 'WeChat Pay', 'Bank kartasi'])
    keyboard.append([tr('back', context)])
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,  resize_keyboard=True)
    update.message.reply_text("Qabul qilinishi yo'lini tanlang:", reply_markup=markup)
    return PAY_TO_RECEIVE_CARD_TYPE

def save_to_receive_card_type(update, context):
    context.user_data['receive_card_type']=update.message.text
    return request_to_receive_card_number(update, context)
    
def request_to_receive_card_number(update, context):
    update.message.reply_text("Karta raqamini kiriting:")
    return PAY_TO_RECEIVE_CARD_NUMBER

def save_to_receive_card_number(update, context):
    context.user_data['receive_card_number']=update.message.text
    return save_to_order(update, context)

def save_to_order(update, context):
    sql = "INSERT INTO orders (uid, pay_type, currency, amount, cny_card_type, cny_card_number, pay_method, last_digits) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING seq, date::date, id"
    data = (update.message.from_user.id, 1, context.user_data['currency'], context.user_data['amount'], context.user_data['receive_card_type'], context.user_data['receive_card_number'], context.user_data['pay_method'], context.user_data['last_digits'])
    cursor.execute(sql, data)
    res = cursor.fetchone()
    db.commit()
    transaction_id = "UZS"+str(res[1]).replace('-', '')+"{:06d}".format(int(res[0]))
    update.message.reply_text("Sizning tranzaksiya raqamingiz: "+ transaction_id)
    sql = "UPDATE orders SET transaction_id = %s WHERE id = %s"
    data = (transaction_id, res[2])
    cursor.execute(sql, data)    
    db.commit()
    update.message.reply_text(vtr('wait_receive', context))
    return main_choice(update, context)

def request_to_china_card(update, context):
    keyboard = [[tr('back', context)]]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,  resize_keyboard=True)
    update.message.reply_text(vtr('send_step_2', context), reply_markup=markup)
    return TO_CHINA_CARD

def save_to_china_card(update, context):
    context.user_data['card']=update.message.text
    update.message.reply_text(vtr('wait_send', context))    
    return main_choice(update, context)

def request_from_china_currency(update, context):
    keyboard=[]
    keyboard.append(['CNY', 'UZS'])
    keyboard.append([tr('back', context)])
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,  resize_keyboard=True)
    update.message.reply_text(tr('currency_to_receive', context), reply_markup=markup)
    return FROM_CHINA_CURRENCY
    
def save_from_china_currency(update, context):
    context.user_data['currency']=update.message.text
    return request_from_china_amount(update, context)

def request_from_china_amount(update, context):
    keyboard=[[tr('back', context)]]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,  resize_keyboard=True)
    update.message.reply_text(tr('amount_to_receive', context), reply_markup=markup)
    return FROM_CHINA_AMOUNT



def save_from_china_amount(update, context):
    amount = int(update.message.text)*100
    if context.user_data['currency']=="UZS":
        uzs = int(get_uzs()[1])
        cny=int(get_cny()[0])/100.0
        delta = amount/uzs
        sql = "SELECT min_point, max_point, uzs_rate, cny_rate from tariff_rates where %s>min_point AND %s<=max_point;"
        data=(delta, delta)
        cursor.execute(sql, data)
        res = cursor.fetchone()
        if res:
            context.user_data['amount']=amount
            s="Komissiya: "+ printnum(res[3]/100.0) + ' yuan'
            s+='\n'
            s+="Qabul qilinadi: "+ printnum(amount/100.0) + ' so\'m'
            s+='\n'
            context.user_data['fee'] = math.ceil(amount/float(uzs)*cny/100.0 + res[3]/100.0)
            s+="Jo'natiladi: " + printnum(amount/100.0)+' / '+printnum(uzs)+' x ' +printnum(cny)+' + '+printnum(int(res[3])/100.0)+' = '+printnum(context.user_data['fee']) + " yuan"
#            s+="Jo'natiladi: (" + printnum(amount/100.0)+' + '+printnum(int(res[2])/100.0)+') / '+printnum(uzs)+' x ' +printnum(cny)+' = '+ printnum(int(((amount-int(res[2]))/float(uzs))*cny/100.0)) + " yuan"
            update.message.reply_text(s)
            return request_pay_method(update, context)
    if context.user_data['currency']=="CNY":
        uzs = int(get_uzs()[1])
        cny=int(get_cny()[0])/100.0
        delta = amount/cny
        sql = "SELECT min_point, max_point, uzs_rate, cny_rate from tariff_rates where %s>min_point AND %s<=max_point;"
        data=(delta, delta)
        cursor.execute(sql, data)
        res = cursor.fetchone()
        if res:
            context.user_data['amount']=amount
            s="Komissiya: "+ printnum(res[3]/100.0) + ' yuan'
            s+='\n'
            s+="Qabul qilinadi: (" + printnum(amount/100.0)+' - '+printnum(int(res[3])/100.0)+') / '+printnum(cny)+' x ' +printnum(uzs)+' = ' + printnum(math.ceil(((amount-int(res[3]))/float(cny))*uzs/100.0)) + " so'm"
            s+='\n'
            context.user_data['fee'] = amount/100.0
            s+="Jo'natiladi: "+ printnum(context.user_data['fee']) + ' yuan'
            update.message.reply_text(s)
            return request_pay_method(update, context)
            

def request_pay_method(update, context):
    keyboard=[]
    keyboard.append(['Alipay', 'WeChat Pay', 'Bank kartasi'])
    keyboard.append([tr('back', context)])
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,  resize_keyboard=True)
    update.message.reply_text("To'lov turini tanlang:", reply_markup=markup)
    return PAY_METHOD_CHOICE

def alipay_method(update, context):
    context.user_data['pay_method']="alipay"
    s = "Alipay: 0000 0000 0000 0000.\nShu raqamga {} yuan o'tkazing va davom etish tugmasini bosing.".format(printnum(context.user_data['fee']))
    return pay_wait(update, context, s)

def wechatpay_method(update, context):
    context.user_data['pay_method']="wechatpay"
    s = "WeChat Pay: 0000 0000 0000 0000.\nShu raqamga {} yuan o'tkazing va davom etish tugmasini bosing.".format(printnum(context.user_data['fee']))
    return pay_wait(update, context, s)

def card_method(update, context):
    context.user_data['pay_method']="card"
    s = "China Card: 0000 0000 0000 0000.\nShu raqamga {} yuan o'tkazing va davom etish tugmasini bosing.".format(printnum(context.user_data['fee']))
    return pay_wait(update, context, s)

def pay_wait(update, context, s):
    keyboard=[]
    keyboard.append(['Davom etish'])
    keyboard.append([tr('back', context)])
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,  resize_keyboard=True)
    update.message.reply_text(s, reply_markup=markup)
    return PAY_WAIT_CHOICE

def payment_confirmation(update, context):
    update.message.reply_text("To'lovni amalga oshirgandan keyin keladigan tranzaksiyaning oxirgi 5ta raqamini kiriting:")
    return PAY_CONFIRMATION_CHOICE

def confirm_payment(update, context):
    context.user_data['last_digits']=update.message.text
    return request_receive_card_type(update, context)


def request_receive_card_type(update, context):
    keyboard=[]
    keyboard.append(['UzCard', 'HUMO'])
    keyboard.append([tr('back', context)])
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,  resize_keyboard=True)
    update.message.reply_text("Karta turini tanlang:", reply_markup=markup)
    return PAY_RECEIVE_CARD_TYPE

def save_receive_card_type(update, context):
    context.user_data['receive_card_type']=update.message.text
    return request_receive_card_number(update, context)
    
def request_receive_card_number(update, context):
    update.message.reply_text("Karta raqamini kiriting:")
    return PAY_RECEIVE_CARD_NUMBER

def save_receive_card_number(update, context):
    context.user_data['receive_card_number']=update.message.text
    return save_order(update, context)

def save_order(update, context):

    sql = "INSERT INTO orders (uid, pay_type, currency, amount, uz_card_type, uz_card_number, pay_method, last_digits) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING seq, date::date, id"
    data = (update.message.from_user.id, 0, context.user_data['currency'], context.user_data['amount'], context.user_data['receive_card_type'], context.user_data['receive_card_number'], context.user_data['pay_method'], context.user_data['last_digits'])
    cursor.execute(sql, data)
    res = cursor.fetchone()
    db.commit()
    transaction_id = "CNY"+str(res[1]).replace('-', '')+"{:06d}".format(int(res[0]))
    update.message.reply_text("Sizning tranzaksiya raqamingiz: "+ transaction_id)
    sql = "UPDATE orders SET transaction_id = %s WHERE id = %s"
    data = (transaction_id, res[2])
    cursor.execute(sql, data)    
    db.commit()
    update.message.reply_text(vtr('wait_receive', context))
    return main_choice(update, context)

def rules_and_tariffs(update, context):
    update.message.reply_text(vtr('rules', context))
    return main_choice(update, context)    

def how_to_send(update, context):
    update.message.reply_text(vtr('how_to_send', context))
    return main_choice(update, context)

def request_receive_confirmation_image(update, context):
    keyboard = [[tr('back', context)]]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,  resize_keyboard=True)
    update.message.reply_text(tr('image_to_send', context), reply_markup=markup)
    return RECEIVE_CONFIRMATION_IMAGE

def save_receive_confirmation_image(update, context):
    context.user_data['image']=update.message.text
    return request_receive_confirmation_card(update, context)

def request_receive_confirmation_card(update, context):
    keyboard = [[tr('back', context)]]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,  resize_keyboard=True)
    update.message.reply_text(tr('receive_confirmation_card_send', context), reply_markup=markup)
    return RECEIVE_CONFIRMATION_CARD

def save_receive_confirmation_card(update, context):
    context.user_data['card']=update.message.text
    update.message.reply_text(vtr('wait_confirmation', context))
    return main_choice(update, context)

def our_contacts(update, context):
    update.message.reply_text(vtr('our_contacts', context))
    return main_choice(update, context)

def history(update, context):
    sql="SELECT transaction_id, amount, currency from orders WHERE uid=%s ORDER by id desc limit 10"
    data = (update.message.from_user.id, )
    cursor.execute(sql, data)
    res = cursor.fetchall()
    s="Sizning o'tkazmalaringiz (oxirgi 10tasi olinadi):\n"
    for i in range(len(res)):
        s+='<b>'+res[i][0]+'</b>: '+printnum(int(res[i][1])/100.0)+' '+res[i][2]
        s+='\n'
    update.message.reply_html(s)
    return main_choice(update, context)

def clear_context(context):
    if 'image' in context.user_data:
        del context.user_data['image']
    if 'card' in context.user_data:
        del context.user_data['card']
    if 'amount' in context.user_data:
        del context.user_data['amount']

def error(update, context):
    logger.warning('Update "%s" caused error "%s"', update, context.error)
    print(list(context))
    try:
        update.effective_message.reply_text(tr('error', context))
    except:
        pass

def cancel(update, context):
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.first_name)
    update.message.reply_text('Bye! I hope we can talk again some day.',
                              reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

sql = "SELECT * from words"
words = db_execute(sql)
#update_currency_regularly()
defaults = Defaults(parse_mode=ParseMode.HTML)
updater = Updater(config.main_token, use_context=True, defaults=defaults)
dp = updater.dispatcher
conv_handler = ConversationHandler(
entry_points=[
    CommandHandler('start', start)
],
states={
    LANGUAGE_CHOICE: [
                  MessageHandler(Filters.regex(regex_prepare(truz('lang'))),
                        uzbek_choice),
                  MessageHandler(Filters.regex(regex_prepare(trru('lang'))),
                        russian_choice),
                  MessageHandler(Filters.all, do_nothing)
    ],
    PHONE_CHOICE: [MessageHandler(Filters.contact,
                        phone_auto),
                  MessageHandler(Filters.regex('^\+998\d{9}$'),
                        phone_manual),
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        start),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        start),
                  MessageHandler(Filters.all, do_nothing)
                  ],

    MAIN_CHOICE: [
                  MessageHandler(Filters.regex(regex_prepare(truz('transfer_money'))),
                        transfer_choice),
                  MessageHandler(Filters.regex(regex_prepare(trru('transfer_money'))),
                        transfer_choice),
                  MessageHandler(Filters.regex(regex_prepare(truz('history'))),
                        history),
                  MessageHandler(Filters.regex(regex_prepare(trru('history'))),
                        history),
                  MessageHandler(Filters.regex(regex_prepare(truz('rules_and_tariffs'))),
                        rules_and_tariffs),
                  MessageHandler(Filters.regex(regex_prepare(trru('rules_and_tariffs'))),
                        rules_and_tariffs),
                  MessageHandler(Filters.regex(regex_prepare(truz('how_to_send'))),
                        how_to_send),
                  MessageHandler(Filters.regex(regex_prepare(trru('how_to_send'))),
                        how_to_send),
                  MessageHandler(Filters.regex(regex_prepare(truz('receive_confirmation'))),
                        request_receive_confirmation_image),
                  MessageHandler(Filters.regex(regex_prepare(trru('receive_confirmation'))),
                        request_receive_confirmation_image),
                  MessageHandler(Filters.regex(regex_prepare(truz('our_contacts'))),
                        our_contacts),
                  MessageHandler(Filters.regex(regex_prepare(trru('our_contacts'))),
                        our_contacts),
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        start),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        start),
                  MessageHandler(Filters.all, do_nothing)
    ],
    TRANSFER_CHOICE: [
                  MessageHandler(Filters.regex(regex_prepare(truz('to_china'))),
                        request_to_china_currency),
                  MessageHandler(Filters.regex(regex_prepare(trru('to_china'))),
                        request_to_china_currency),
                  MessageHandler(Filters.regex(regex_prepare(truz('from_china'))),
                        request_from_china_currency),
                  MessageHandler(Filters.regex(regex_prepare(trru('from_china'))),
                        request_from_china_currency),
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        main_choice),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        main_choice),
                  MessageHandler(Filters.all, do_nothing)
    ],
    TO_CHINA_CURRENCY:[
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        main_choice),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        main_choice),
                  MessageHandler(Filters.text,
                        save_to_china_currency),
                  MessageHandler(Filters.all, do_nothing)
    ],
    TO_CHINA_AMOUNT:[
                  MessageHandler(Filters.regex('^[1-9]\d*$'),
                        save_to_china_amount),
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        request_to_china_currency),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        request_to_china_currency),
                  MessageHandler(Filters.all, do_nothing)
    ],
    PAY_TO_METHOD_CHOICE:[
                  MessageHandler(Filters.regex('^UzCard$'),
                        save_to_pay_method),
                  MessageHandler(Filters.regex('^HUMO'),
                        save_to_pay_method),
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        request_to_china_amount),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        request_to_china_amount),
                  MessageHandler(Filters.all, do_nothing)
    ],
    PAY_TO_WAIT_CHOICE:[
                  MessageHandler(Filters.regex('^Davom etish$'),
                        to_payment_confirmation),
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        request_to_pay_method),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        request_to_pay_method),
                  MessageHandler(Filters.all, do_nothing)
    ],
    PAY_TO_CONFIRMATION_CHOICE:[
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        pay_to_wait),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        pay_to_wait),
                  MessageHandler(Filters.text,
                        to_confirm_payment),
                  MessageHandler(Filters.all, do_nothing)
    ],
    PAY_TO_RECEIVE_CARD_TYPE:[
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        to_payment_confirmation),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        to_payment_confirmation),
                  MessageHandler(Filters.text,
                        save_to_receive_card_type),
                  MessageHandler(Filters.all, do_nothing)
    ],
    PAY_TO_RECEIVE_CARD_NUMBER:[
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        request_to_receive_card_type),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        request_to_receive_card_type),
                  MessageHandler(Filters.text,
                        save_to_receive_card_number),
                  MessageHandler(Filters.all, do_nothing)
    ],
    TO_CHINA_CARD:[
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        request_from_china_amount),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        request_from_china_amount),
                  MessageHandler(Filters.text,
                        save_to_china_card),
                  MessageHandler(Filters.all, do_nothing)
    ],
    FROM_CHINA_CURRENCY:[
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        main_choice),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        main_choice),
                  MessageHandler(Filters.text,
                        save_from_china_currency),
                  MessageHandler(Filters.all, do_nothing)
    ],
    FROM_CHINA_AMOUNT:[
                  MessageHandler(Filters.regex('^[1-9]\d*$'),
                        save_from_china_amount),
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        request_from_china_currency),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        request_from_china_currency),
                  MessageHandler(Filters.all, do_nothing)
    ],
    PAY_METHOD_CHOICE:[
                  MessageHandler(Filters.regex('^Alipay$'),
                        alipay_method),
                  MessageHandler(Filters.regex('^WeChat Pay$'),
                        wechatpay_method),
                  MessageHandler(Filters.regex('^Bank kartasi$'),
                        card_method),
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        request_from_china_amount),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        request_from_china_amount),
                  MessageHandler(Filters.all, do_nothing)
    ],
    PAY_WAIT_CHOICE:[
                  MessageHandler(Filters.regex('^Davom etish$'),
                        payment_confirmation),
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        request_pay_method),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        request_pay_method),
                  MessageHandler(Filters.all, do_nothing)
    ],
    PAY_CONFIRMATION_CHOICE:[
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        pay_wait),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        pay_wait),
                  MessageHandler(Filters.text,
                        confirm_payment),
                  MessageHandler(Filters.all, do_nothing)
    ],
    PAY_RECEIVE_CARD_TYPE:[
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        payment_confirmation),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        payment_confirmation),
                  MessageHandler(Filters.text,
                        save_receive_card_type),
                  MessageHandler(Filters.all, do_nothing)
    ],
    PAY_RECEIVE_CARD_NUMBER:[
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        request_receive_card_type),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        request_receive_card_type),
                  MessageHandler(Filters.text,
                        save_receive_card_number),                        
                  MessageHandler(Filters.all, do_nothing)
    ],
    HISTORY:[
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        main_choice),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        main_choice),
                  MessageHandler(Filters.all, do_nothing)
    ],
    RECEIVE_CONFIRMATION_IMAGE:[
                  MessageHandler(Filters.photo,
                        save_receive_confirmation_image),
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        main_choice),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        main_choice),
                  MessageHandler(Filters.all, do_nothing)
    ],
    
    RECEIVE_CONFIRMATION_CARD:[
                  MessageHandler(Filters.text,
                        save_receive_confirmation_card),
                  MessageHandler(Filters.regex(regex_prepare(truz('back'))),
                        main_choice),
                  MessageHandler(Filters.regex(regex_prepare(trru('back'))),
                        main_choice),
                  MessageHandler(Filters.all, do_nothing)
    ],
},
fallbacks=[MessageHandler(Filters.regex('^Done$'), cancel)],
allow_reentry = True)
dp.add_handler(conv_handler)
dp.add_handler(MessageHandler(Filters.all, echo))
dp.add_error_handler(error)
updater.start_polling()
updater.idle()
