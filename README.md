# Github Hosted PyPI

Make all your private packages accessible in one place with this github hosted PyPI index.

Built using warehub

---

## Features

* **:octocat: Github-hosted**
* **Template ready to deploy**
* **Add Packages via GitHub Issue**

## Description

This repository is a Github page used as a PyPI index, conform to [PEP503](https://www.python.org/dev/peps/pep-0503/).

You can use it to group all your packages in one place, and access it easily through `pip`, almost like any other package publicly available!

## Get started

* Use this template and create your own
  repository: [![Generic badge](https://img.shields.io/badge/Use%20this%20template-blueviolet.svg)](https://github.com/Mimer29or40/GithubPyPI/generate)
* Go to `Settings` of your repository, and enable Github Pages
* Create an issue with the template
* Make a Pull Request to merge the generated branch.
* You're ready to go! Visit `<user>.github.io/<repo_name>` to see your PyPI index

## Configuring

* `path`: **Required** - The path to the base directory where warehub will write files.
* `database`: **Required** - The path to the database file relative to `path`.
* `url`: **Required** - The url to the website homepage. Usually in the form `<user>.github.io/<repo_name>`
* `title`: **Optional** - The title of the website.
    * Default: `Personal Python Package Index`
* `description`: **Optional** - Text to show on the homepage.
    * Default: `Welcome to your private Python package index!`
* `image_url`: **Optional** - The url to an image that will be the favicon and will be displayed on every page
    * Default: `https://pypi.org/static/images/logo-small.95de8436.svg`

## Adding Packages

To add new packages to the repository. Simply create an Issue using the available template and enter the information.

* **`Repository`:** The path to the github page. Usually in the form `<user>/<repo_name>`
* **`Domain`:** The domain to access the github api from. This is mainly used for enterprise github users
    * Default: `https://api.github.com`
* **`Username`:** The username to use for authentication
    * Default: `env.WAREHUB_USERNAME`
* **`Password`:** The password to use for authentication
    * Default: `env.WAREHUB_USERNAME`

Sample:

```markdown
## Add Repository Packages Form

- **Repository:** User123/PythonPackage
- **Domain:**
- **Username:**
- **Password:**
```

### Note: Username and Passwords

It is bad practice to supply username's and password's in plain text especially when hosted on a public platform.

To prevent this vulnerability, warehub can pull this information from the environment variables `WAREHUB_USERNAME` and `WAREHUB_PASSWORD`. This is the recommended way to provide a
username and password.

[Defining Environment Variables in Github](https://docs.github.com/en/actions/security-guides/encrypted-secrets)

## FAQ

#### Q. Is it secure?

As you may know, standard Github pages are public so any packages that are imported to it will be public as well. It is only possible to make private repo's with GitHub Pro, GitHub
Team, GitHub Enterprise Cloud, and GitHub Enterprise Server.

#### Q. What happen behind the scenes?

When running `pip install <package_name> --extra-index-url <repo_url>`, the following happen:

1. `pip` will look at `https://pypi.org/`, the default, public index, trying to find a package with the specified name.
2. If it can't find, it will look at `<repo_url>`.
3. If the package is found there, the link of the package is returned to `pip <repo_link>`.
4. `pip` install any missing dependency with the same steps.

_Authentication happen at step 4, when cloning the repository._

#### Q. What are the best practices for using this PyPI index?

The single best practice is using Github releases. This allow your package to have a version referred by a specific tag.  
To do this:

* Push your code in a repository.
* Create a new Github release. Ensure you follow [semantic versioning](https://semver.org/). It will create a tag.
* When adding the package to this index, warehub will find all releases and add each release file.
* To install a package with a specific version, use `pip install <package_name>==<version> --extra-index-url <repo_url>`

#### Q. What if the name of my package is already taken by a package in the public index?

You can just specify a different name for your indexed package. Just give it a different name in the form when registering it.

For example if you have a private package named `tensorflow`, when you register it in this index, you can name it `my_cool_tensorflow`, so there is no name-collision with the
public package `tensorflow`.  
Then you can install it with `pip install my_cool_tensorflow --extra-index-url <repo_url>`.

Then from `python`, you can just do:

```python
import tensorflow
```

_Note: While it's possible to do like this, it's better to have a unique name for your package, to avoid confusion._

#### Q. How to add this repository to IDE's (PyCharm, etc)?

To add this repository to an IDE, simply add `<repo_url>/simple` to the list of repositories. This mirrors the api of pypi so it should work as long as your IDE supports pypi.

---

**_If you have any questions or ideas to improve this FAQ, please open a PR / blank issue!_**

## Contribute

Issues and PR are welcome!

If you come across anything weird / that can be improved, please get in touch!

## References

**This is greatly inspired from [this repository](https://github.com/ceddlyburge/python-package-server).**  
It's just a glorified version, with cleaner pages and github actions for easily adding, updating and removing packages from your index.

Also check the [blogpost](https://www.freecodecamp.org/news/how-to-use-github-as-a-pypi-server-1c3b0d07db2/) of the original author!

Another reference use were the official pypi software, twine and warehouse. They were used to make sure that all the required information was inputted.

---

_Icon used in the page was made by [Freepik](https://www.flaticon.com/authors/freepik) from [Flaticon](https://www.flaticon.com/)_
