import json
import os


def main():
    # Get the context from the environment variable
    context = json.loads(os.environ['GITHUB_CONTEXT'])
    print(context)
    # issue_ctx = context['event']['issue']
    # title = issue_ctx['title']
    #
    # if title.startswith("🟢"):
    #     register(issue_ctx)
    #
    # if title.startswith("🔵"):
    #     update(issue_ctx)
    #
    # if title.startswith("🔴"):
    #     delete(issue_ctx)


if __name__ == "__main__":
    main()
