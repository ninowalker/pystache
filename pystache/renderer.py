# coding: utf-8

"""
This module provides a Renderer class to render templates.

"""

import cgi
import os
import sys

from .context import Context
from .loader import DEFAULT_EXTENSION
from .loader import Loader
from .reader import Reader
from .renderengine import RenderEngine


# The quote=True argument causes double quotes to be escaped,
# but not single quotes:
#   http://docs.python.org/library/cgi.html#cgi.escape
DEFAULT_ESCAPE = lambda s: cgi.escape(s, quote=True)


class Renderer(object):

    """
    A class for rendering mustache templates.

    This class supports several rendering options which are described in
    the constructor's docstring.  Among these, the constructor supports
    passing a custom template loader.

    Here is an example of passing a custom template loader to render a
    template using partials loaded from a string-string dictionary.

    >>> partials = {'partial': 'Hello, {{thing}}!'}
    >>> renderer = Renderer(loader=partials)
    >>> renderer.render('{{>partial}}', {'thing': 'world'})
    u'Hello, world!'

    """

    # TODO: rename the loader argument to "partials".
    def __init__(self, loader=None, file_encoding=None, default_encoding=None,
                 decode_errors='strict', search_dirs=None, file_extension=None,
                 escape=None):
        """
        Construct an instance.

        Arguments:

          loader: an object (e.g. pystache.Loader or dictionary) for custom
            partial loading during the rendering process.
                The loader should have a get() method that accepts a string
            and returns the corresponding template as a string, preferably
            as a unicode string.  If there is no template with that name,
            the method should either return None (as dict.get() does) or
            raise an exception.
                If this argument is None, partial loading takes place using
            the normal procedure of reading templates from the file system
            using the Loader-related instance attributes (search_dirs,
            file_encoding, etc).

          escape: the function used to escape variable tag values when
            rendering a template.  The function should accept a unicode
            string (or subclass of unicode) and return an escaped string
            that is again unicode (or a subclass of unicode).
                This function need not handle strings of type `str` because
            this class will only pass it unicode strings.  The constructor
            assigns this function to the constructed instance's escape()
            method.
                The argument defaults to `cgi.escape(s, quote=True)`.  To
            disable escaping entirely, one can pass `lambda u: u` as the
            escape function, for example.  One may also wish to consider
            using markupsafe's escape function: markupsafe.escape().

          file_encoding: the name of the encoding of all template files.
            This encoding is used when reading and converting any template
            files to unicode.  All templates are converted to unicode prior
            to parsing.  Defaults to the default_encoding argument.

          default_encoding: the name of the encoding to use when converting
            to unicode any strings of type str encountered during the
            rendering process.  The name will be passed as the encoding
            argument to the built-in function unicode().  Defaults to the
            encoding name returned by sys.getdefaultencoding().

          decode_errors: the string to pass as the errors argument to the
            built-in function unicode() when converting to unicode any
            strings of type str encountered during the rendering process.
            Defaults to "strict".

          search_dirs: the list of directories in which to search for
            templates when loading a template by name.  Defaults to the
            current working directory.  If given a string, the string is
            interpreted as a single directory.

          file_extension: the template file extension.  Defaults to "mustache".
            Pass False for no extension (i.e. for extensionless files).

        """
        if default_encoding is None:
            default_encoding = sys.getdefaultencoding()

        if escape is None:
            escape = DEFAULT_ESCAPE

        # This needs to be after we set the default default_encoding.
        if file_encoding is None:
            file_encoding = default_encoding

        if file_extension is None:
            file_extension = DEFAULT_EXTENSION

        if search_dirs is None:
            search_dirs = os.curdir  # i.e. "."

        if isinstance(search_dirs, basestring):
            search_dirs = [search_dirs]

        self.decode_errors = decode_errors
        self.default_encoding = default_encoding
        self.escape = escape
        self.file_encoding = file_encoding
        self.file_extension = file_extension
        # TODO: rename self.loader to self.partials.
        self.loader = loader
        self.search_dirs = search_dirs

    def _to_unicode_soft(self, s):
        """
        Convert a basestring to unicode, preserving any unicode subclass.

        """
        # Avoid the "double-decoding" TypeError.
        return s if isinstance(s, unicode) else self.unicode(s)

    def _to_unicode_hard(self, s):
        """
        Convert a basestring to a string with type unicode (not subclass).

        """
        return unicode(self._to_unicode_soft(s))

    def _escape_to_unicode(self, s):
        """
        Convert a basestring to unicode (preserving any unicode subclass), and escape it.

        Returns a unicode string (not subclass).

        """
        return unicode(self.escape(self._to_unicode_soft(s)))

    def unicode(self, s):
        """
        Convert a string to unicode, using default_encoding and decode_errors.

        Raises:

          TypeError: Because this method calls Python's built-in unicode()
            function, this method raises the following exception if the
            given string is already unicode:

              TypeError: decoding Unicode is not supported

        """
        # TODO: Wrap UnicodeDecodeErrors with a message about setting
        # the default_encoding and decode_errors attributes.
        return unicode(s, self.default_encoding, self.decode_errors)

    def _make_context(self, context, **kwargs):
        """
        Initialize the context attribute.

        """
        if context is None:
            context = {}

        if isinstance(context, Context):
            context = context.copy()
        else:
            context = Context(context)

        if kwargs:
            context.push(kwargs)

        return context

    def _make_reader(self):
        """
        Create a Reader instance using current attributes.

        """
        return Reader(encoding=self.file_encoding, decode_errors=self.decode_errors)

    def _make_loader(self):
        """
        Create a Loader instance using current attributes.

        """
        reader = self._make_reader()
        loader = Loader(reader=reader, search_dirs=self.search_dirs, extension=self.file_extension)

        return loader

    def _make_load_partial(self):
        """
        Return the load_partial function to pass to RenderEngine.__init__().

        """
        if self.loader is None:
            loader = self._make_loader()
            return loader.get

        # Otherwise, create a load_partial function from the custom loader
        # that satisfies RenderEngine requirements (and that provides a
        # nicer exception, etc).
        loader = self.loader

        def load_partial(name):
            template = loader.get(name)

            if template is None:
                # TODO: make a TemplateNotFoundException type that provides
                # the original loader as an attribute.
                raise Exception("Partial not found with name: %s" % repr(name))

            # RenderEngine requires that the return value be unicode.
            return self._to_unicode_hard(template)

        return load_partial

    def _make_render_engine(self):
        """
        Return a RenderEngine instance for rendering.

        """
        load_partial = self._make_load_partial()

        engine = RenderEngine(load_partial=load_partial,
                              literal=self._to_unicode_hard,
                              escape=self._escape_to_unicode)
        return engine

    def read(self, path):
        """
        Read and return as a unicode string the file contents at path.

        This class uses this method whenever it needs to read a template
        file.  This method uses the file_encoding and decode_errors
        attributes.

        """
        reader = self._make_reader()
        return reader.read(path)

    # TODO: add unit tests for this method.
    def load_template(self, template_name):
        """
        Load a template by name from the file system.

        """
        loader = self._make_loader()
        return loader.get(template_name)

    def render_path(self, template_path, context=None, **kwargs):
        """
        Render the template at the given path using the given context.

        Read the render() docstring for more information.

        """
        template = self.read(template_path)
        return self.render(template, context, **kwargs)

    def render(self, template, context=None, **kwargs):
        """
        Render the given template using the given context.

        Returns a unicode string.

        Arguments:

          template: a template string that is either unicode or of type str.
            If the string has type str, it is first converted to unicode
            using this instance's default_encoding and decode_errors
            attributes.  See the constructor docstring for more information.

          context: a dictionary, Context, or object (e.g. a View instance).

          **kwargs: additional key values to add to the context when
            rendering.  These values take precedence over the context on
            any key conflicts.

        """
        engine = self._make_render_engine()
        context = self._make_context(context, **kwargs)

        # RenderEngine.render() requires that the template string be unicode.
        template = self._to_unicode_hard(template)

        rendered = engine.render(template, context)

        return unicode(rendered)
