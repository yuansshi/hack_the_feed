"""Direct Gemini example using only this project's designated credential."""
import time

from gemini_provider import GeminiClient, TEXT_MODEL, load_project_key, output_text


def main():
    with GeminiClient(load_project_key()) as client:
        interaction = client.create({
            'model': TEXT_MODEL,
            'input': 'Explain briefly how source photos and floor plans can guide a continuous property walkthrough video.',
            'background': True,
            'store': True,
        })
        print('Interaction:', interaction['id'])
        deadline = time.monotonic() + 180
        while interaction.get('status') in ('queued', 'in_progress') and time.monotonic() < deadline:
            time.sleep(2)
            interaction = client.get(interaction['id'])
        print(output_text(interaction) if interaction.get('status') == 'completed'
              else 'Resume this interaction by its ID; no duplicate request was submitted.')


if __name__ == '__main__':
    main()
