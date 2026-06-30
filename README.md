# psaintemarie-recipes

These are my recipes for AutoPkg. If you use them, click the ★  Star button at the top of the page to show your support.

Many of these recipes were created with the aid of [Recipe Robot](https://github.com/homebysix/recipe-robot), an app you should definitely check out.

## Installation

To add my repo to your Mac (with AutoPkg and Git already installed), run this command:

```
autopkg repo-add psaintemarie-recipes
```
## Dependencies

Some of my recipes have parent recipes that live in another repo:

- `Codeium/Windsurf.munki.recipe` requires `com.github.almenscorner.download.Windsurf`, from [autopkg/almenscorner-recipes](https://github.com/autopkg/almenscorner-recipes).
- `MicrosoftOneDrive/MicrosoftOneDriveUniversal.munki.recipe` requires `com.github.rtrouton.download.microsoftuniversalonedrive`, from [autopkg/rtrouton-recipes](https://github.com/autopkg/rtrouton-recipes).

Add those repos (e.g. `autopkg repo-add rtrouton-recipes`) before running the recipes above. For any other recipe, refer to its `ParentRecipe` identifier to determine which repo, if any, you'll need.

## Known issues

Do you have a problem with one of my recipes? [Check the issues](https://github.com/autopkg/psaintemarie-recipes/issues) to see whether a known problem exists. If not, just [submit an issue](https://github.com/autopkg/psaintemarie-recipes/issues/new) so I can take a look.

## Submissions

Forks/pulls/issues are more than welcome. Let's improve together.
