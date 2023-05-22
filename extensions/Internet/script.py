import re
import asyncio
import modules.shared as shared
import gradio as gr

import extensions
from modules import chat

from EdgeGPT import Chatbot, ConversationStyle
from modules.chat import replace_all
from modules.text_generation import (encode, get_max_prompt_length, get_encoded_length)
from modules.extensions import apply_extensions


BingOutput=None
RawBingString=None
BingString=None
ShowBingString=False
OverwriteWord=False
PrintUserInput=False
PrintWholePrompt=False
PrintRawBingString=False
PrintBingString=False

ChosenWord="Hey Neo"
BingContext1="Important informations:"
BingContext2="Now answer the following question based on the given informations. If my sentence starts with \"Hey Neo\" ignore that part, I'm referring to you anyway, so don't say you are Neo.\n"

print("\nThanks")

params = {
    'ShowBingString': False,
    'OverwriteWord': False,
    'PrintUserInput': False,
    'PrintWholePrompt': False,
    'PrintRawBingString': False,
    'PrintBingString': False,
}

def input_modifier(string):
    global UserInput
    global BingOutput
    global RawBingString
    global ChosenWord
    # Reset Bing output shown in the webui
    RawBingString=None

    UserInput=string
    # Find out if the chosen word appears in the sentence.
    # If you want to change the chosen word, change "Hey Bing"
    BingOutput = re.search(ChosenWord, UserInput)

    if params['ShowBingString']:
        global ShowBingString
        ShowBingString=True
    else:
        ShowBingString=False

    if params['OverwriteWord']:
        global OverwriteWord
        OverwriteWord=True
    else:
        OverwriteWord=False

    if params['PrintUserInput']:
        global PrintUserInput
        PrintUserInput=True
        print("User input:\n", UserInput)
    else:
        PrintUserInput=False
    
    if params['PrintWholePrompt']:
        global PrintWholePrompt
        PrintWholePrompt=True
    else:
        PrintWholePrompt=False
    
    if params['PrintRawBingString']:
        global PrintRawBingString
        PrintRawBingString=True
    else:
        PrintRawBingString=False

    if params['PrintBingString']:
        global PrintBingString
        PrintBingString=True
    else:
        PrintBingString=False

    if(BingOutput!=None) and not OverwriteWord:
        shared.processing_message = "*Is typing...*"
    elif OverwriteWord:
        shared.processing_message = "*Is typing...*"
    else:
        shared.processing_message = "*Is typing...*"
    return string
    

    # Default prompt + BingString (if requested)
def custom_generate_chat_prompt(user_input, state, **kwargs):
    impersonate = kwargs['impersonate'] if 'impersonate' in kwargs else False
    _continue = kwargs['_continue'] if '_continue' in kwargs else False
    also_return_rows = kwargs['also_return_rows'] if 'also_return_rows' in kwargs else False
    is_instruct = state['mode'] == 'instruct'
    rows = [state['context'] if is_instruct else f"{state['context'].strip()}\n"]
    min_rows = 3

    # Finding the maximum prompt size
    chat_prompt_size = state['chat_prompt_size']
    if shared.soft_prompt:
        chat_prompt_size -= shared.soft_prompt_tensor.shape[1]

    max_length = min(get_max_prompt_length(state), chat_prompt_size)

    # Building the turn templates
    if 'turn_template' not in state or state['turn_template'] == '':
        if is_instruct:
            template = '<|user|>\n<|user-message|>\n<|bot|>\n<|bot-message|>\n'
        else:
            template = '<|user|>: <|user-message|>\n<|bot|>: <|bot-message|>\n'
    else:
        template = state['turn_template'].replace(r'\n', '\n')

    replacements = {
        '<|user|>': state['name1'].strip(),
        '<|bot|>': state['name2'].strip(),
    }

    user_turn = replace_all(template.split('<|bot|>')[0], replacements)
    bot_turn = replace_all('<|bot|>' + template.split('<|bot|>')[1], replacements)
    user_turn_stripped = replace_all(user_turn.split('<|user-message|>')[0], replacements)
    bot_turn_stripped = replace_all(bot_turn.split('<|bot-message|>')[0], replacements)

    # Building the prompt
    i = len(shared.history['internal']) - 1
    while i >= 0 and get_encoded_length(''.join(rows)) < max_length:
        if _continue and i == len(shared.history['internal']) - 1:
            rows.insert(1, bot_turn_stripped + shared.history['internal'][i][1].strip())
        else:
            rows.insert(1, bot_turn.replace('<|bot-message|>', shared.history['internal'][i][1].strip()))

        string = shared.history['internal'][i][0]
        if string not in ['', '<|BEGIN-VISIBLE-CHAT|>']:
            rows.insert(1, replace_all(user_turn, {'<|user-message|>': string.strip(), '<|round|>': str(i)}))

        i -= 1

    if impersonate:
        min_rows = 2
        rows.append(user_turn_stripped.rstrip(' '))
    elif not _continue:

        #Adding BingString
        async def EdgeGPT():
            global UserInput
            global RawBingString
            global PrintRawBingString
            bot = await Chatbot.create()
            response = await bot.ask(prompt=UserInput, conversation_style=ConversationStyle.creative)
            # Select only the bot response from the response dictionary
            for message in response["item"]["messages"]:
                if message["author"] == "bot":
                    bot_response = message["text"]
            # Remove [^#^] citations in response
            RawBingString = re.sub('\[\^\d+\^\]', '', str(bot_response))
            await bot.close()
            return RawBingString
        
        # Different ways to run the same EdgeGPT function:
        # From chosen word
        if(BingOutput!=None) and not OverwriteWord:
            asyncio.run(EdgeGPT())
        # of from OverwriteWord button
        elif OverwriteWord:
            asyncio.run(EdgeGPT())
        # When Bing has given his answer we print (if requested) and save 
        # the output
        if RawBingString != None and not "":
            if PrintRawBingString:
                print("\nNeo output:\n", RawBingString)
            BingString=BingContext1 + RawBingString + "\n" + BingContext2
            if PrintBingString:
                print("\nNeo output + context:\n", BingString)
            # Add Bing output to character memory
            rows.append(BingString)

        # Adding the user message
        if len(user_input) > 0:
            rows.append(replace_all(user_turn, {'<|user-message|>': user_input.strip(), '<|round|>': str(len(shared.history["internal"]))}))

        # Adding the Character prefix
        rows.append(apply_extensions("bot_prefix", bot_turn_stripped.rstrip(' ')))

    while len(rows) > min_rows and get_encoded_length(''.join(rows)) >= max_length:
        rows.pop(1)

    prompt = ''.join(rows)
    if also_return_rows:
        return prompt, rows
    else:
        return prompt
    

def output_modifier(string):
    """
    This function is applied to the model outputs.
    """
    global BingOutput
    global RawBingString
    global ShowBingString
    if ShowBingString:
        string = "Neo:" + str(RawBingString) + "\n\n\n" + string
        return string
    else:
        return string


def bot_prefix_modifier(string):
    """
    This function is only applied in chat mode. It modifies
    the prefix text for the Bot and can be used to bias its
    behavior.
    """
    
    return string


def FunChooseWord(CustomWordRaw):
    global ChosenWord
    ChosenWord = CustomWordRaw
    return CustomWordRaw

def Context1Func(Context1Raw):
    global BingContext1
    BingContext1 = Context1Raw
    return Context1Raw

def Context2Func(Context2Raw):
    global BingContext2
    BingContext2 = Context2Raw
    return Context2Raw


def ui():
    # with gr.Accordion("Instructions", open=False):
    #     with gr.Box():
    #         gr.Markdown(
    #             """
    #             To use it, just start the prompt with Hey Bing; it doesn't start if you don't use uppercase and lowercase as in the example. You can change the activation word from Internet options. If the output is strange turn on Show Bing Output to see the result of Bing, maybe you need to correct your question.
                
    #             """)
            
    with gr.Accordion("Internet options", open=False):
        with gr.Row():
            ShowBingString = gr.Checkbox(value=params['ShowBingString'], label='Show Neo Output')
        with gr.Row():
            WordOption = gr.Textbox(label='Choose and use a word to activate Internet', placeholder="Choose your word. Empty = Hey Neo")
            OverwriteWord = gr.Checkbox(value=params['OverwriteWord'], label='No need of word just connect to Internet .')
        with gr.Accordion("Internet context", open=False):
            with gr.Row():
                Context1Option = gr.Textbox(label='Choose context-1', placeholder="First context, is injected before the Neo output. Empty = default context-1")
            with gr.Row():
                Context2Option = gr.Textbox(label='Choose context-2', placeholder="Second context, is injected after the Neo output. Empty = default context-2")
            # with gr.Row():
            #     gr.Markdown(
            #         """
            #         You can see the default context (with Bing outp in the middle) by turning on the fourth option in "Print in console options": "Print Bing string in command console".
            #         """)
            
    # with gr.Accordion("Print in console options", open=False):
    #     with gr.Row():
    #         PrintUserInput = gr.Checkbox(value=params['PrintUserInput'], label='Print User input in command console. The user input will be fed first to Neo, and then to the default bot.')
    #     with gr.Row():
    #         PrintWholePrompt = gr.Checkbox(value=params['PrintWholePrompt'], label='Print whole prompt in command console. Prompt has: context, Neo search output, and user input.')
    #     with gr.Row():
    #         PrintRawBingString = gr.Checkbox(value=params['PrintRawBingString'], label='Print raw Neo string in command console. The raw  strNeoing is the clean Neo output.')
    #     with gr.Row():
    #         PrintBingString = gr.Checkbox(value=params['PrintBingString'], label='Print Neo string in command console. It is the Neo output + a bit of context, to let the default bot understand what to do with it.')
    

    ShowBingString.change(lambda x: params.update({"ShowBingString": x}), ShowBingString, None)
    WordOption.change(fn=FunChooseWord, inputs=WordOption)
    OverwriteWord.change(lambda x: params.update({"OverwriteWord": x}), OverwriteWord, None)
    
    Context1Option.change(fn=Context1Func, inputs=Context1Option)
    Context2Option.change(fn=Context2Func, inputs=Context2Option)

    # PrintUserInput.change(lambda x: params.update({"PrintUserInput": x}), PrintUserInput, None)
    # PrintWholePrompt.change(lambda x: params.update({"PrintWholePrompt": x}), PrintWholePrompt, None)
    # PrintRawBingString.change(lambda x: params.update({"PrintRawBingString": x}), PrintRawBingString, None)
    # PrintBingString.change(lambda x: params.update({"PrintBingString": x}), PrintBingString, None)
