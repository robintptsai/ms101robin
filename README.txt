Release note for [Master Shares]

production url: ms101robin.appspot.com
source: https://bitbucket.org/keakon/doodle/
designed by: robintptsai@gmail.com


Installation:

1. app.yaml: Replace "YOUR_APPID" to your own app ID. If you don't want to use root path for your blog, you should change the URL mapping of admin.py and blog.py. If you use Python 2.7, rename app27.yaml to app.yaml and use it instead.
2. cron.yaml: If you don't want to use root path for your blog, you should change the URLs.
3. setting.py: See the comments besides the setting variables. If you don't want to use root path for your blog, you should change BLOG_HOME_RELATIVE_PATH.
4. default_error.html, over_quota.html and timeout.html: Replace "YOUR_BLOG_TITLE" to your blog's title, and replace "YOUR_BLOG_SUB_TITLE" to sub title. If you don't want to use root path for your blog, you should change the URLs of each links. You may also need change them to fit your own theme.
5. static\favicon.ico: Replace to your own favicon.
6. static\theme and template: Put your own themes into these folders, and change "THEMES" in setting.py.
7. static\markitup\sets\bbcode\set.js: If you don't want to use root path for your blog, you should change previewParserPath.
8. static\theme\freshpress\js\maintain.js: If you don't want to use root path for your blog, you should change the admin path.


Updating:

If you didn't change the source code of Doodle except what the Installation part asked you to do:
1. Download the new version.
2. Configure it as what the Installation part says.
3. Deploy the new version. (You can backup the old version.)
4. If there are some instructions for a particular version, you should also follow it.

If you need to do some enhancement for Doodle:
1. You'd better to use Mercurial to pulling the changeset and merge it with your own code. Otherwise, you have to compare and find the changes manually.
2. Pay more attention about the changes in setting.py.
3. Deploy the new version.
4. If there are some instructions for a particular version, you should also follow it.


Import & Export:

The files which name begin with "bulkloader" is used to import and export data.
Doodle only support to import data from Discuz! and WordPress, but you need handle customized fields by yourself.
You need follow these steps to upload data:
1. Run the queries in bulkloader_discuz.sql or bulkloader_wordpress.sql via phpMyAdmin, export the result to an XML file.
2. Put the XML file into "dontupload" folder, then run bulkloader_discuz.bat or bulkloader_wordpress.bat to upload.
3. You may need change the URL parameter and the settings of bulkloader_discuz.yaml and bulkloader_wordpress.yaml (especially the xpath_to_nodes parameter).
You can also import data from other blog systems by studying its database schema, build a bulkloader.yaml file and transform function by yourself.


Backup & Restore:

There is a Backup tab in the Manage blog page. You can backup and restore data there.
The backup file is JSON format compressed by gzip, you can't import it to other blog system directly.
It's recommended to use split_backup.py to split the backup file before you import it.


Posting article by email:

Use the admin account to send an email to write@YOUR_APP_ID.appspotmail.com.
You can change "write" to what ever you like. Just open app.yaml, find out "/_ah/mail/write@.+\.appspotmail\.com", then modify "write" to other string.
The email title will be the article title, and its content will be the article content. The email content format can be HTML or plain text.


How to make a theme:

If you know the basic grammar of PHP and Python, it should be easy for you to port a theme form WordPress to Doodle.
You can reference to the implementation of existing themes. The template files is under "template" folder, and static files is under "static\theme" folder.
If you want reuse the existing JavaScript files, you'd better keep the DOM structure same as the koi theme, otherwise you may need to do some changes of these JavaScript files.

Doodle uses pyTenjin as its template engine, its grammar is similar to Python.
1. The Python sentences are surrounded by "<?py ?>". Each sentence per line, starts form the begining of the line.
2. Use tab for Indentation, use '#endfor', '#endif', '#endwhile' and so on to close corresponding sentences.
3. #{} means output as string, ${} means output as string and also escape to HTML entity. It can contain any available Python expressions,  even call functions.
4. <?PY ?> contains preprocessed sentences which will only be run once. The variables and functions in it cannot be used by <?py ?>, #{} or ${}, neither can it use the variables or functions in <?py ?> or template parameters.
5. #{{}} and ${{}} is similar as #{} and ${}, but it can only use the variables and functions in <?PY ?>.
6. Sub template can be included by include() function.
7. You can use "if not_cached()" and "echo_cached()" to cache a part of template.
8. If you get an error duo to the template file is end by <?py ?> sentence, you can add a blank line at the end of file.

Notice: The pyTenjin version has been updated to 1.0.1 since Doodle 1.2, if you use self-designed theme, you should read the change log of pyTenjin. eg: tenjin.helpers.html need to be change to tenjin.html.