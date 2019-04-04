def decimal(x,precision=9):
    s = ("%."+str(precision)+"f") % x
    if '.' not in s or s[-1] != '0':
        return s
    n = -1
    while s[n] == '0':
        n -= 1
    s = s[:n+1]
    if s[-1] == '.':
        return s[:-1]
    else:
        return s
    
if __name__ == '__main__':
    print(decimal(4.4))