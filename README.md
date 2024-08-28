
# DocumentGPT: Confluence Documents Search Bot

<p align="center">
<a href=""><img src="docs/resources/DocumentGPT-Logo.png" alt="DocumentGPT logo: Enable GPT to work in software company, In Company Confluence Space, GPT Collect all informantion of Space and Answer about Company Informantion for employee with Slack Chat" width="150px"></a>
</p>

<p align="center">
<b> In Company Confluence Space, GPT Collect all informantion of Space and Tell Company Informantion to employee with Slack Chat. Please stop searching for company documents directly in Confluence. </b>
</p>

## News
🚀 Aug. 25, 2024: [v1.0]

## Get Started  
	1. You have to get below API's key and password & Fill (main.py, Reset.py, update.py)'s API section.  
		a. Confluence  
		b. Slack  
		c. GPT (code is set for Azure GPT)  
	2. You can make your raw_data for GPT Chat Bot through raw_data file's code  
		a. Make raw_filter.txt (which includes summarization of all page in Confluence) through starting reset.py  
		b. update.py is not necessary (it is for updating changes in page not for starting)  
	3. After making base data in raw_data, you have to create your own bot in Slack.  
		a. The way for bot can be found on the internet.  
		b. After creating bot, main.py will be the main code for bot (I used Docker for operating this code in the background)  
	4. You can Chat with your bot successfully!!  