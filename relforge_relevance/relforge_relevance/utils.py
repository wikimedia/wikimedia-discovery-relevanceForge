def asciify(the_string):
    if isinstance(the_string, (int, bool)):
        return str(the_string)
    # Round trip through a bytes object to get the extended characters replaced
    # with xml style character references (for later insertion into html output).
    return the_string.encode('ascii', 'xmlcharrefreplace').decode('ascii')
