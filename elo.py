def expected_score(p1, p2):
    a = (p2 - p1) / 400
    b = 10 ** a
    c = 1 + b
    d = 1 / c
    return d

def update(r, e, s, k=32):
    x = s - e
    y = k * x
    z = r + y
    return z

def match(p1_rating, p2_rating, result, k=32):
    e1 = expected_score(p1_rating, p2_rating)
    e2 = expected_score(p2_rating, p1_rating)
    
    r1_new = update(p1_rating, e1, result, k)
    r2_new = update(p2_rating, e2, 1 - result, k)
    
    r1_temp = round(r1_new)
    r2_temp = round(r2_new)
    
    if r1_temp == r1_new:
        r1_final = r1_temp
    else:
        r1_final = int(r1_new + 0.5 if r1_new > r1_temp else r1_new - 0.5)
    
    if r2_temp == r2_new:
        r2_final = r2_temp
    else:
        r2_final = int(r2_new + 0.5 if r2_new > r2_temp else r2_new - 0.5)

    return r1_final, r2_final

