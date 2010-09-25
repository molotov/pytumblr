__version__='0.1.0'
__doc__="pyTumblr %s - http://github.com/molotov/pytumblr" % __version__


from xml.dom.minidom import parseString
from urllib import urlopen
from urllib import urlencode
from unicodedata import normalize
import time
from getpass import getpass
from urlparse import urlparse
from Queue import Queue



def prompt_options(question, options, default=None):
    out = question
    opts = []
    for item in options:
        opts.append("\t{index}.) {item}".format(
            index=options.index(item) + 1, 
            item=item,
        ))
    
    ask = 'Option: '
    out = "\n\n%s\n%s\n%s" % (out, "\n".join(opts), ask)
    
    
    def invalid_response(resp):
        return not (resp > 0 and resp <= len(options))
    
    try:
        try:
            resp = int(raw_input(out))
        except ValueError:
            resp = None
        
        # check that resp is an index in the list
        while invalid_response(resp):
            print 'Invalid response. Please try again.'
            resp = int(raw_input(ask))
    
    except KeyboardInterrupt:
        # be silent, just exit.
        print "Exiting.\n"
        exit(1)
    
    return resp

def get_node(node, key):
    """
    Convenience for getting a single-child node in a tree.
    """
    value = node.getElementsByTagName(key)
    if value:
        return value[0]

def val(node):
    """
    Expecting: <some-node>'Thing'</some-node> this will return: 'Thing'.
    """
    if node:
        return node.firstChild.nodeValue

def _x(s=None):
    if s:
        print s
    import pdb; pdb.set_trace()


class Post(object):
    """
    A tumblr post. Can have text/video/audio/images related to it.
    
    _attrs: A list of xml attributes to extract from each post. Other common
        post data (such as tags) are manually pulled out during initialization.
    """
    _attrs = [
        'date',
        'date-gmt', 
        'format', 
        'id', 
        'reblog-key',
        'slug',
        'type',
        'unix-timestamp',
        'url',
        'url-with-slug'
    ]
    
    def __init__(self, post):
        # store this post for inspection later.
        self.__post = post
        print post.toprettyxml()
        
        # grab common attributes
        self.attrs = {}
        for k in self._attrs:
            self.attrs[k] = post.getAttribute(k)
        
        # handle tags
        tags = post.getElementsByTagName('tag')
        self.attrs['tags'] = []
        for tag in tags:
            self.attrs['tags'].append(val(tag))
            
        # let subclassing objects parse their own things.
        self.parse(post)
        
    def parse(self, node):
        """
        Subclasses must implement parse for the xml node passed in.
        
        @param node: The xml node.
        @type node: <DOM Element>
        """
        raise NotImplementedError()
    
    def to_dict(self):
        """
        This is called when the post is being cast to a dictionary on it's way
        to being sent to Tumblr. This must be implemented by subclasses.
        """
        raise NotImplementedError()
        
    def __str__(self):
        return 'Post: %s' % self.__class__.__name__
        
    def dict(self):
        """
        Casting to a dict will be used when creating http POST requests.
        
        This base class provides some meta information, but note that it does
        not provide current 'date' functionality. 
        """
        d = self.to_dict()
        
        # Tumblr api at this time does not provide for sending the 
        # 'Let people photo reply' option.
        meta = {
            'generator':__doc__,
            'date': self.attrs['date'],
            'format': self.attrs['format'],
            'type': self.type,
            'tags': ','.join(self.attrs['tags']),
        }
        d.update(meta)
        return d


class RegularPost(Post):
    type = 'regular'
    def parse(self, node):
        """
        <post type="regular" ... >
            <regular-title>...</regular-title>
            <regular-body>...</regular-body>
        </post>
        """
        self.title = val(get_node(node, 'regular-title'))
        self.body = val(get_node(node, 'regular-body'))

    def to_dict(self):
        """
        Requires at least one:
        title
        body (HTML allowed)
        """
        d = {}
        if self.title:
            d['title'] = self.title
        if self.body:
            d['body'] = self.body
        return d


class LinkPost(Post):
    type = 'link'
    def parse(self, node):
        """
        <post type="link" ... >
            <link-text>...</link-text>
            <link-url>...</link-url>
        </post>
        """
        self.text = val(get_node(node, 'link-text'))
        self.url = val(get_node(node, 'link-url'))
        self.description = val(get_node(node, 'link-description'))
    
    def to_dict(self):
        """
        name (optional)
        url
        description (optional, HTML allowed)
        
        TODO: This isn't handling descriptions yet, though the XML doesn't 
        look like it returns description. Investigate further.
        
        Also, yes the api/read version is called 'link-text' and the api/write
        version expects 'name'. Odd.
        """
        d = {
            'url':self.url
        }
        if self.text:
            d['name'] = self.text
        if self.description:
            d['description'] = self.description
            
        return d


class QuotePost(Post):
    type = 'quote'
    def parse(self, node):
        """
        <post type="quote" ... >
            <quote-text>...</quote-text>
            <quote-source>...</quote-source>
        </post>
        """
        self.text = val(get_node(node, 'quote-text'))
        self.source = val(get_node(node, 'quote-source'))

    def to_dict(self):
        """
        Tumblr provides quote-text on api/read, but expects 'quote' on api/write.
        
        quote
        source (optional, HTML allowed)
        """
        d = {
            'quote':self.text,
        }
        if self.source:
            d['source'] = self.source

        return d


class PhotoPost(Post):
    type = 'photo'
    def parse(self, node):
        """
        <post type="photo" ... >
            <photo-caption>...</photo-caption>
            <photo-url max-width="500">...</photo-url>
            <photo-url max-width="400">...</photo-url>
            ...
        </post>
        """
        
        self.caption = val(get_node(node, 'photo-caption'))
        self.link_url = val(get_node(node, 'photo-link-url'))
        urls = node.getElementsByTagName('photo-url')
        self.urls = {}
        
        # this sets up the urls for a photo, not sure why the API returns
        # <photo-url> as well as <photo-set>
        for url in urls:
            _url = val(url)
            parsed = urlparse(_url)
            if parsed.netloc.endswith('tumblr.com'):
                url_check = urlopen(_url)
                _url = url_check.geturl()
                print 'resetting url to: %s' % _url
                
            self.urls[int(url.getAttribute('max-width'))] = _url
            
        # handle the case where there is a photo-set
        self.photos = []
        photo_set = node.getElementsByTagName('photoset')
        for photo in photo_set:
            photo_urls = photo.getElementsByTagName('photo-url')
            url = None
            for inner_url in photo_urls:
                # the tumblr xml returns 1280, 500, 400, 250, 100, 75 max-width
                # I'm gonna assume that 1280 is the original image and not
                # worry about messing with the others...
                # Dear Future Self, I hate you. Sincerely, Past Self.
                if inner_url.getAttribute('max-width') == 1280:
                    url = val(inner_url)
                    break
            photo = {
                'caption':photo.getAttribute('caption'),
                'url':url
            }
            self.photos.append(photo)
    
    def to_dict(self):
        """
        In copying, I am not going to fetch and republish image data. Just
        provide the URL that Tumblr has already created.
        
        @TODO: Handle click-through-urls.
        @TODO: Find out how permanent asset urls are for Tumblr. If I delete
        the old blog, will that photo be destroyed or moved?
        
        source - The URL of the photo to copy. This must be a web-accessible URL, not a local file or intranet location.
        data - An image file. See File uploads below.
        caption (optional, HTML allowed)
        click-through-url (optional)
        """
        d = {
            'source': self.urls[max([int(i) for i in self.urls.keys()])],
        }
        if self.caption:
            d['caption'] = self.caption
        if self.link_url:
            d['click-through-url'] = self.link_url
            
        return d


class ConversationPost(Post):
    type = 'conversation'
    def parse(self, node):
        """
        <post type="conversation" ... >
            <conversation-title>...</conversation-title>
            <conversation-text>...</conversation-text>
            <conversation>
                <line name="..." label="...">...</line>
                <line name="..." label="...">...</line>
                ...
            </conversation>
        </post>
        """
        self.title = val(get_node(node, 'conversation-title'))
        self.text = val(get_node(node, 'conversation-text'))
        
        self.conversation = []
        for line in node.getElementsByTagName('conversation'):
            d = {
                'name':line.getAttribute('name'),
                'label':line.getAttribute('label'),
                'value':val(line),
            }
            self.conversation.append(d)

    def to_dict(self):
        """
        title (optional)
        conversation
        """
        return {
            'title':self.title,
            'conversation':self.text,
        }


class VideoPost(Post):
    type = 'video'
    def parse(self, node):
        """
        <post type="video" ... >
            <video-caption>...</video-caption>
            <video-source>...</video-source>
            <video-player>...</video-player>
        </post>
        """
        self.caption = val(get_node(node, 'video-caption'))
        self.source = val(get_node(node, 'video-source'))
        self.player = val(get_node(node, 'video-player'))

    def to_dict(self):
        """
        Requires either embed or data, but not both.
        embed - Either the complete HTML code to embed the video, or the URL 
            of a YouTube video page.
        data - A video file for a Vimeo upload.
        title (optional) - Only applies to Vimeo uploads.
        caption (optional, HTML allowed)
        """
        return {
            'embed':self.player,
            'caption':self.caption,
        }


class AudioPost(Post):
    type = 'audio'
    def parse(self, node):
        """
        <post type="audio" ... >
            <audio-caption>...</audio-caption>
            <audio-player>...</audio-player>
        </post>
        """
        self.caption = val(get_node(node, 'audio-caption'))
        self.player = val(get_node(node, 'audio-player'))

    def to_dict(self):
        """
        data - An audio file. Must be MP3 or AIFF format.
        externally-hosted-url (optional, replaces data) - Create a post that 
            uses this externally hosted audio-file URL instead of having 
            Tumblr copy and host an uploaded file. Must be MP3 format. No size
            or duration limits are imposed on externally hosted files.
        caption (optional, HTML allowed)
        
        @TODO: Curses. Tumblr provides caption and player, but not source.
        Looking like I'll have to parse the player for it's source or something.
        """
        raise NotImplementedError()


class AnswerPost(Post):
    def parse(self, node):
        """
        <post type="answer" ... >
            <question>...</question>
            <answer>...</answer>
        </post>
        """
    def to_dict(self):
        """
        Tumblr doesn't support this post type at this time for writing.
        """
        raise Exception('Tumblr does not support api/write of Answer posts.')


class Blog(object):
    """
    A blog or 'group' of posts according to Tumblr.
    """
    
    def __init__(self, config_data):
        """
        config_data = {
            'avatar_url': a,
            'post_count': b,
            'title': c,
            'url': d,
        }
        """
        for k,v in config_data.iteritems():
            setattr(self, k, v)
        
        self.post_queue = Queue()
    
    def add_post(self, post):
        print 'Adding post: %s' % post  
        self.post_queue.put(post)
    
    def post_count(self):
        return self.post_queue.qsize()
    
    def __str__(self):
        return '<Blog: {title}({url})>'.format(title=self.title, url=self.url)
    
    def __iter__(self):
        """
        Yield posts that have been added. These posts will be in the local
        post_queue.
        """
        while not self.post_queue.empty():
            yield self.post_queue.get()

    
class Account(object):
    """
    A tumblr account.
    """
    
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.blogs = []
        self.blog_index = {}

    def add_blog(self, blog):
        self.blogs.append(blog)
        self.blog_index[blog.title] = blog
    
    def find_blog(self, title):
        return self.blog_index[title]
    
    def __str__(self):
        
        return '< Account object "{email}": {blogs} >'.format(
            email=self.email, 
            blogs=', '.join(str(item) for k, item in self.blog_index.items())
        )
        

class PyTumblr(object):
    """
    Class for interacting with Tumblr.
    """
    
    def __init__(self):
        self.last_request = {}
        self.last_response = None
    
    def request(self, url, data, get=None):
        """
        Proxy the request to tumblr.
        
        @param url: The url to request.
        @type url: string
        @param data: The dict object indicating POST parameters.
        @type data: dict
        """
        
        # *sigh*
        clean = {}
        for k,v in data.items():
            clean[k] = normalize('NFKD', unicode(v)).encode('ascii','ignore')
        
        clean = urlencode(clean)
        self.last_request = {'url':url, 'data':clean}
        
        resp = urlopen(url, clean)
        self.last_response = resp
        
        if resp:
            return resp.read()
    
    def authenticate(self, account):
        """
        Get authentication and account info based on an Account object. Tumblr
        also returns basic info about all the blogs on an account, so while we
        have that info, we'll set that up and add those Blogs to the Accounts.
        """
        data = {
            'email':account.email,
            'password':account.password,
        }
        result = self.request('http://www.tumblr.com/api/authenticate', data)
        
        # authenticate returns xml, so parse the string.
        try:
            x = parseString(result)
        except:
            # the request failed in some way.
            raise Exception('Authentication to Tumblr failed. %s' % data)
        
        
        # I don't really care about the <user> node at this time.
        blogs = x.getElementsByTagName('tumblelog')
        for blog in blogs:
            b = Blog({
                'avatar_url': blog.getAttribute('avatar-url'),
                'post_count': blog.getAttribute('posts'),
                'title': blog.getAttribute('title'),
                'url': blog.getAttribute('url'),
            })
            account.add_blog(b)

    def find_posts(self, blog):
        """
        This method will block. Just wait until we're done getting all of the 
        posts
        
        start - The post offset to start from. The default is 0.
        num - The number of posts to return. The default is 20, and the 
            maximum is 50.
        type - The type of posts to return. If unspecified or empty, all types
            of posts are returned. Must be one of text, quote, photo, link, 
            chat, video, or audio.
        id - A specific post ID to return. Use instead of start, num, or type.
        filter - Alternate filter to run on the text content. Allowed values:
            text - Plain text only. No HTML.
            none - No post-processing. Output exactly what the author entered.
            (Note: Some authors write in Markdown, which will not be converted
            to HTML when this option is used.)
        tagged - Return posts with this tag in reverse-chronological order 
            (newest first). Optionally specify chrono=1 to sort in 
            chronological order (oldest first).
        search - Search for posts with this query.
        state (Authenticated read required) - Specify one of the values draft,
            queue, or submission to list posts in the respective state.
        """
        
        print 'Finding blogs for: %s' % blog.url
        
        
        def fetch_more(start):
            print 'Fetching more posts: {blog}, starting at: {start}'.format(
                blog=blog.title,
                start=start
            )
            
            
            data = {
                'start':start,
                'num':50,
                'filter':'none',
            }
            
            # make sure and rtrim the '/' off this url, or not.
            request_url = '{blog}api/read'.format(blog=blog.url)
            result = self.request(request_url, data)
            try:
                x = parseString(result)
            except Exception, e:
                # the request failed in some way.
                raise Exception('Fetching more posts from Tumblr failed. %s' % data)
            
            posts = x.getElementsByTagName('posts')
            if len(posts):
                posts = posts[0]
            
            
            parsed_posts = []
            
            for post in posts.getElementsByTagName('post'):
                # factorizer-izationism
                _type = post.getAttribute('type').title()
                klass = '%sPost' % _type
                p = globals()[klass](post)
                parsed_posts.append(p)
            
            return parsed_posts
        
        not_finished = True
        posts = []
        start = 0
        while not_finished:
            posts = fetch_more(start)
            if not posts:
                not_finished = False
            else:
                for post in posts:
                    blog.add_post(post)
                start = start + len(posts)
                
        print 'Found %s posts.' % blog.post_queue.qsize()

    def copy_from_to(self, src_account, src_blog, dest_account, dest_blog):
        """
        Copy all posts form src_blog to dest_blog.
        """
        print 'Posting to %s' % dest_blog
        
        post_count = 0
        total = src_blog.post_queue.qsize()
        begin_time = time.time()
        for post in src_blog:
            start_time = time.time()
            post_count += 1
            
            # the 'group' parameter wasn't very clear. Have determined that
            # it's the url (versus something like blog name/title).
            request = {
                'email': dest_account.email,
                'password': dest_account.password,
                'group': dest_blog.url
            }
            request.update(post.dict())
            result = self.request('http://www.tumblr.com/api/write', request)
            
            stop_time = time.time()
            if self.last_response.code != 201:
                print 'Copy for post failed, requeing.'
                src_blog.add_post(post)
                import pdb; pdb.set_trace()
            else:
                print 'Posted %s post. %s of %s (took %ss)' % (request['type'], post_count, total, stop_time-start_time)
        end_time = time.time()
        
        print 'Took %ss total to post %s posts.' % (end_time-begin_time, total)




if __name__=='__main__':
    
    api = PyTumblr()
    
    src_email = raw_input('Source account email: ')
    src_pass = getpass('Source account password: ')
    src_account = Account(src_email, src_pass)
    api.authenticate(src_account)
    
    dest_email = raw_input('Destination account email: ')
    dest_pass = getpass('Destination account password: ')
    dest_account = Account(dest_email, dest_pass)
    api.authenticate(dest_account)
    
    print 'Copying from {src_account} to {dest_account}...'.format(
        src_account=src_account.email, dest_account=dest_account.email,
    )
    
    src_titles = [v.title for k, v in src_account.blog_index.items()]
    src_blog_option = prompt_options(
        'Which blog from {src_account.email} would you like to copy?'.format(src_account=src_account),
        src_titles
    )
    src_blog_option = src_titles[src_blog_option-1]
    
    dest_titles = [v.title for k, v in dest_account.blog_index.items()]
    dest_blog_option = prompt_options(
        'Which blog from {dest_account.email} would you like to copy to?'.format(dest_account=dest_account),
        dest_titles
    )
    dest_blog_option = dest_titles[dest_blog_option-1]
    
    src_blog = src_account.find_blog(src_blog_option)
    dest_blog = dest_account.find_blog(dest_blog_option)
    
    print 'Copying all blogs from {src_account.email}:{src_blog} to {dest_account.email}:{dest_blog}'.format(
        src_account=src_account, 
        dest_account=dest_account,
        src_blog=src_blog,
        dest_blog=dest_blog,
    )
    
    api.find_posts(src_blog)
    
    # for now since this is a very specific use-case, I'm just saving when 
    # I copy them.
    api.copy_from_to(src_account, src_blog, dest_account, dest_blog)

