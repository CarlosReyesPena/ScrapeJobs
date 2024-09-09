# ScriptJobs

ScriptJobs is an automation project designed to simplify the job application process. It takes a list of companies as input, scrapes important information about each company, automatically generates personalized cover letters, and sends applications via email.

## Features

- **Automated Scraping**: Retrieves key information about the given companies (e.g., industry, key personnel, etc.).
- **Automatic Cover Letter Generation**: Creates personalized cover letters using the collected data for each company.
- **Automated Email Sending**: Automatically sends the cover letters and resumes to companies.

## Project Structure

- `CompanyCraw.py`: Handles scraping company information.
- `CoverBuilder.py`: Generates customized cover letters.
- `Mailsender.py`: Manages sending emails to companies.
- `main.py`: The main entry point that coordinates the entire process.
- `setup.py`: Contains setup instructions and dependency management.

## Requirements

- Python 3.x
- LaTeX (for cover letter generation)
- Python libraries:
  - `requests`
  - `beautifulsoup4`
  - `groq`
  - `langdetect`

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/CarlosReyesPena/ScrapeJobs.git
