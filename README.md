pytumblr
========

A Python module to interact with Tumblr's API.

Mainly used to copy a blog from one account to another. The copying process uses gevent, so copying actions take place asynchronously.

Usage
-----

$ ls
config.ini
pytumblr.py

$ ./pytumblr.py
Reading config...

Copying from 'Account 2' to 'Account 1'.

Which blog from 'Account 2' would you like to copy?
    1.) Some blog
    2.) Another Blog
    3.) Thingy

Number: 2


Note: Tumblr's API does not allow blog creation at this time. You must copy posts to an existing blog.

Which blog from 'Account 1' woudl you like to copy TO?
    1.) Blarg
    2.) Blooorg
    3.) Bleerg

Number: 3

Copying all posts from 'Account 2: Another Blog' to 'Account 1: Bleerg'.

Copied post: 1123552778
Copied post: 1375727863 + images
Copied post: 1123552778
Copied post: 2609854737
Copied post: 3862760399 + audio
Copied post: 1212159776 + video
Copied post: 4368935920

Done!

See pytumblr.log for a more detailed report of what happened.




