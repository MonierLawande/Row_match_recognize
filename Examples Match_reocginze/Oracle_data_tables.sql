CREATE TABLE stock_price (
    Company    VARCHAR2(10),
    Price_date DATE,
    Price      NUMBER
);

drop table stock_price;

INSERT ALL
    INTO stock_price VALUES ('A', DATE '2020-10-01', 50)
    INTO stock_price VALUES ('B', DATE '2020-10-01', 89)
    INTO stock_price VALUES ('A', DATE '2020-10-02', 36)
    INTO stock_price VALUES ('B', DATE '2020-10-02', 24)
    INTO stock_price VALUES ('A', DATE '2020-10-03', 39)
    INTO stock_price VALUES ('B', DATE '2020-10-03', 37)
    INTO stock_price VALUES ('A', DATE '2020-10-04', 42)
    INTO stock_price VALUES ('B', DATE '2020-10-04', 63)
    INTO stock_price VALUES ('A', DATE '2020-10-05', 30)
    INTO stock_price VALUES ('B', DATE '2020-10-05', 65)
    INTO stock_price VALUES ('A', DATE '2020-10-06', 47)
    INTO stock_price VALUES ('B', DATE '2020-10-06', 56)
    INTO stock_price VALUES ('A', DATE '2020-10-07', 71)
    INTO stock_price VALUES ('B', DATE '2020-10-07', 50)
    INTO stock_price VALUES ('A', DATE '2020-10-08', 80)
    INTO stock_price VALUES ('B', DATE '2020-10-08', 54)
    INTO stock_price VALUES ('A', DATE '2020-10-09', 75)
    INTO stock_price VALUES ('B', DATE '2020-10-09', 30)
    INTO stock_price VALUES ('A', DATE '2020-10-10', 63)
    INTO stock_price VALUES ('B', DATE '2020-10-10', 32)
SELECT * FROM dual;

SELECT * FROM stock_price;



drop table employees;

CREATE TABLE employees (
    id          NUMBER,
    name        VARCHAR2(50),
    department  VARCHAR2(50),
    region      VARCHAR2(50),
    hire_date   DATE,
    salary      NUMBER
);


INSERT ALL
    INTO employees VALUES (1, 'Alice',   'Sales', 'West', DATE '2021-01-01', 1200)
    INTO employees VALUES (2, 'Bob',     'Sales', 'West', DATE '2021-01-02', 1300)
    INTO employees VALUES (3, 'Charlie', 'Sales', 'West', DATE '2021-01-03', 900)
    INTO employees VALUES (4, 'Diana',   'Sales', 'West', DATE '2021-01-04', 1100)
SELECT * FROM dual;







CREATE TABLE op2 (
    id         NUMBER,
    seq        NUMBER,
    step       NUMBER,
    event_type VARCHAR2(20),
    value      NUMBER
);


INSERT ALL
    INTO op2 VALUES (1, 1, 1, 'start', 100)
    INTO op2 VALUES (2, 1, 2, 'middle', 200)
    INTO op2 VALUES (3, 1, 3, 'end', 300)

    INTO op2 VALUES (4, 2, 1, 'middle', 250)
    INTO op2 VALUES (5, 2, 2, 'start', 150)
    INTO op2 VALUES (6, 2, 3, 'end', 350)

    INTO op2 VALUES (7, 3, 1, 'start', 175)
    INTO op2 VALUES (8, 3, 2, 'end', 275)
    INTO op2 VALUES (9, 3, 3, 'middle', 375)

    INTO op2 VALUES (10, 4, 1, 'end', 225)
    INTO op2 VALUES (11, 4, 2, 'middle', 325)
    INTO op2 VALUES (12, 4, 3, 'start', 425)
SELECT * FROM dual;



drop table orders;
CREATE TABLE orders (
    customer_id VARCHAR2(50),
    order_date  DATE,
    price       NUMBER
);


INSERT ALL
    INTO orders VALUES ('cust_1', DATE '2020-05-11', 100)
    INTO orders VALUES ('cust_1', DATE '2020-05-12', 200)
    INTO orders VALUES ('cust_2', DATE '2020-05-13', 8)
    INTO orders VALUES ('cust_1', DATE '2020-05-14', 100)
    INTO orders VALUES ('cust_2', DATE '2020-05-15', 4)
    INTO orders VALUES ('cust_1', DATE '2020-05-16', 50)
    INTO orders VALUES ('cust_1', DATE '2020-05-17', 100)
    INTO orders VALUES ('cust_2', DATE '2020-05-18', 6)
SELECT * FROM dual;







CREATE TABLE employee_data (
    id          NUMBER,
    name        VARCHAR2(50),
    department  VARCHAR2(50),
    region      VARCHAR2(50),
    hire_date   DATE,
    salary      NUMBER
);
INSERT ALL
    INTO employee_data VALUES (1, 'Alice',   'Sales',     'West',  DATE '2021-01-01', 1200)
    INTO employee_data VALUES (2, 'Bob',     'Sales',     'West',  DATE '2021-01-02', 1300)
    INTO employee_data VALUES (3, 'Charlie', 'Sales',     'West',  DATE '2021-01-03', 900)
    INTO employee_data VALUES (4, 'Diana',   'Sales',     'West',  DATE '2021-01-04', 1100)

    INTO employee_data VALUES (5, 'Eve',     'Marketing', 'East',  DATE '2021-01-01', 900)
    INTO employee_data VALUES (6, 'Frank',   'Marketing', 'East',  DATE '2021-01-02', 950)
    INTO employee_data VALUES (7, 'Grace',   'Marketing', 'East',  DATE '2021-01-03', 980)
    INTO employee_data VALUES (8, 'Henry',   'Marketing', 'East',  DATE '2021-01-04', 1200)

    INTO employee_data VALUES (9,  'Ivy',    'IT',        'North', DATE '2021-01-01', 1500)
    INTO employee_data VALUES (10, 'Jack',   'IT',        'North', DATE '2021-01-02', 1600)
    INTO employee_data VALUES (11, 'Kate',   'IT',        'North', DATE '2021-01-03', 1700)
    INTO employee_data VALUES (12, 'Leo',    'IT',        'North', DATE '2021-01-04', 1800)

    INTO employee_data VALUES (13, 'Mike',   'HR',        'South', DATE '2021-01-01', 950)
    INTO employee_data VALUES (14, 'Nina',   'HR',        'South', DATE '2021-01-02', 980)
    INTO employee_data VALUES (15, 'Oscar',  'HR',        'South', DATE '2021-01-03', 990)
    INTO employee_data VALUES (16, 'Pam',    'HR',        'South', DATE '2021-01-04', 995)
SELECT * FROM dual;





























SELECT *
FROM stock_price
MATCH_RECOGNIZE (
    PARTITION BY Company
    ORDER BY Price_date
    MEASURES
        FIRST(A.Price) AS start_price,
        LAST(A.Price)  AS end_price,
        MATCH_NUMBER() AS match_id
    PATTERN (A B C)
    DEFINE
        B AS B.Price > PREV(B.Price),
        C AS C.Price > PREV(C.Price)
);







SELECT customer_id, start_price, bottom_price, final_price, start_date, final_date
FROM orders
MATCH_RECOGNIZE (
    PARTITION BY customer_id
    ORDER BY order_date
    MEASURES
        A.price              AS start_price,
        LAST(DOWN.price)     AS bottom_price,
        LAST(UP.price)       AS final_price,
        A.order_date         AS start_date,
        LAST(UP.order_date)  AS final_date
    ONE ROW PER MATCH
    AFTER MATCH SKIP PAST LAST ROW
    PATTERN (A DOWN+ UP+)
    DEFINE
        DOWN AS DOWN.price < PREV(DOWN.price),
        UP   AS UP.price   > PREV(UP.price)
);


SELECT customer_id, start_price, final_price, start_date, final_date
FROM orders
MATCH_RECOGNIZE (
    PARTITION BY customer_id
    ORDER BY order_date
    MEASURES
        A.price AS start_price,
        LAST(DOWN.price) AS final_price,
        A.order_date AS start_date,
        LAST(DOWN.order_date) AS final_date
    ONE ROW PER MATCH
    AFTER MATCH SKIP PAST LAST ROW
    PATTERN (A DOWN+)
    DEFINE
        A    AS 1=1,           -- A is always true
        DOWN AS DOWN.price IS NOT NULL AND DOWN.price < 150
);

SELECT customer_id, start_date, end_date, bottom_price
FROM orders
MATCH_RECOGNIZE (
    PARTITION BY customer_id
    ORDER BY order_date
    MEASURES
        A.order_date AS start_date,
        C.order_date AS end_date,
        C.price      AS bottom_price
    PATTERN (A B C)
    DEFINE
        B AS B.price < A.price,
        C AS C.price < B.price
);





SELECT
    customer_id,
    start_price,
    last_b_price AS peak_price,
    last_c_price AS bottom_price,
    last_d_price AS end_price,
    start_date,
    end_date
FROM orders
MATCH_RECOGNIZE (
    PARTITION BY customer_id
    ORDER BY order_date
    MEASURES
        A.price AS start_price,
        LAST(B.price) AS last_b_price,
        LAST(C.price) AS last_c_price,
        LAST(D.price) AS last_d_price,
        A.order_date AS start_date,
        LAST(D.order_date) AS end_date
    PATTERN (A B+ C+ D+)
    DEFINE
        B AS B.price > PREV(B.price),
        C AS C.price < PREV(C.price),
        D AS D.price > PREV(D.price)
);




SELECT *
FROM employee_data
MATCH_RECOGNIZE (
    PARTITION BY department
    ORDER BY hire_date
    MEASURES 
        CLASSIFIER() AS pattern_var,
        MATCH_NUMBER() AS match_num
    ONE ROW PER MATCH
    PATTERN ((A B) | (B A))
    DEFINE 
        A AS salary > 1200,
        B AS salary < 1000
);







SELECT *
FROM employees
MATCH_RECOGNIZE (
    PARTITION BY department, region
    ORDER BY hire_date
    MEASURES 
        A.salary AS starting_salary,
        LAST(C.salary) AS ending_salary,
        MATCH_NUMBER() AS match_num
    ONE ROW PER MATCH
    AFTER MATCH SKIP PAST LAST ROW
    PATTERN (A B+ C+)
    DEFINE 
        A AS A.salary > 1000,
        B AS B.salary < 1000,
        C AS C.salary > 1000
);



SELECT *
FROM employees
MATCH_RECOGNIZE (
    PARTITION BY department, region
    ORDER BY hire_date
    MEASURES 
        salary AS avg_salary
    PATTERN (A+)
    DEFINE 
        A AS A.salary > 1000
);

SELECT
customer_id,
run_start,
run_end
FROM memory.default.orders
MATCH_RECOGNIZE (
PARTITION BY customer_id
ORDER BY order_date
MEASURES
A.order_date AS run_start,
LAST(B.order_date) AS run_end
PATTERN (A B+)
DEFINE
A AS price >= 100,
B AS price > PREV(price)
);


SELECT *
FROM orders
MATCH_RECOGNIZE (
    PARTITION BY customer_id
    ORDER BY order_date
    MEASURES
        A.price AS start_price,
        LAST(B.price) AS bottom_price,    -- fully qualified
        LAST(C.price) AS final_price,     -- fully qualified
        A.order_date AS start_date,
        LAST(C.order_date) AS final_date
    ONE ROW PER MATCH
    AFTER MATCH SKIP PAST LAST ROW
    PATTERN (A B+ C+)
    DEFINE
        B AS B.price < PREV(B.price),
        C AS C.price > PREV(C.price)
);



SELECT *
FROM orders
MATCH_RECOGNIZE (
    PARTITION BY customer_id
    ORDER BY order_date
    MEASURES
        FIRST(A.price) AS start_price,   -- first row of A
        LAST(B.price)  AS bottom_price,  -- last row of B
        LAST(C.price)  AS final_price,   -- last row of C
        FIRST(A.order_date) AS start_date,
        LAST(C.order_date)  AS final_date
    ONE ROW PER MATCH
    PATTERN (A B+ C+)
    DEFINE
        B AS B.price < PREV(B.price),
        C AS C.price > PREV(C.price)
);

SELECT *
FROM employee_data
MATCH_RECOGNIZE (
    PARTITION BY department
    ORDER BY hire_date
    MEASURES
        CLASSIFIER() AS pattern_var,
        salary AS current_salary
    ALL ROWS PER MATCH
    PATTERN (A+)
    DEFINE
        A AS A.salary > 1200
);

SELECT *
FROM orders
MATCH_RECOGNIZE (
    PARTITION BY customer_id
    ORDER BY order_date
    MEASURES
        CLASSIFIER() AS pattern_var,
        MATCH_NUMBER() AS match_num,
        FIRST(A.price) AS start_price,
        FIRST(A.order_date) AS start_date
    ALL ROWS PER MATCH
    PATTERN (A+)
    DEFINE
        A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL
);

SELECT *
FROM orders
MATCH_RECOGNIZE (
    PARTITION BY customer_id
    ORDER BY order_date
    MEASURES
        CLASSIFIER() AS pattern_var,
        MATCH_NUMBER() AS match_num,
        A.price AS price_value,
        A.order_date AS order_value
    ALL ROWS PER MATCH
    PATTERN (A+)
    DEFINE
        A AS A.price > 0
);

SELECT *
FROM orders
MATCH_RECOGNIZE (
    PARTITION BY customer_id
    ORDER BY order_date
    MEASURES
        CLASSIFIER() AS pattern_var,
        MATCH_NUMBER() AS match_num,
        A.price AS price_value,
        A.order_date AS order_value
    ALL ROWS PER MATCH
    PATTERN (A*)
    DEFINE
        A AS A.price < 150
);


SELECT *
FROM  orders
MATCH_RECOGNIZE (
    PARTITION BY customer_id
    ORDER BY order_date
    MEASURES
        CLASSIFIER() AS pattern_var,
        MATCH_NUMBER() AS match_num,
        A.price AS price_value,
        A.order_date AS order_value
    ALL ROWS PER MATCH
    PATTERN (A?)
    DEFINE
        A AS A.price >= 200
);

SELECT *
FROM  orders
MATCH_RECOGNIZE (
    PARTITION BY customer_id
    ORDER BY order_date
    MEASURES
        CLASSIFIER() AS pattern_var,
        MATCH_NUMBER() AS match_num,
        A.price AS price_value,
        A.order_date AS order_value
    ALL ROWS PER MATCH
    PATTERN (A+)
    DEFINE
        A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL
);





SELECT *
FROM orders
MATCH_RECOGNIZE (
    PARTITION BY customer_id
    ORDER BY order_date
    MEASURES
        CLASSIFIER() AS pattern_var,
        MATCH_NUMBER() AS match_num,
        A.price AS price_value,
        A.order_date AS order_value
    ALL ROWS PER MATCH
    PATTERN (A+)
    DEFINE
        A AS A.price < PREV(A.price) OR PREV(A.price) IS NULL
);


SELECT *
FROM orders
MATCH_RECOGNIZE (
    PARTITION BY customer_id
    ORDER BY order_date
    MEASURES
        CLASSIFIER() AS pattern_var,
        MATCH_NUMBER() AS match_num,
        A.price AS price_value,
        A.order_date AS order_value
    ALL ROWS PER MATCH
    PATTERN (A+)
    DEFINE
        A AS A.price > 0
);


SELECT *
FROM orders
MATCH_RECOGNIZE (
    PARTITION BY customer_id
    ORDER BY order_date
    MEASURES
        CLASSIFIER() AS pattern_var,
        MATCH_NUMBER() AS match_num,
        A.price AS price_value,
        A.order_date AS order_value
    ALL ROWS PER MATCH
    PATTERN (A*)
    DEFINE
        A AS A.price < 150
);



SELECT *
FROM orders
MATCH_RECOGNIZE (
    PARTITION BY customer_id
    ORDER BY order_date
    MEASURES
        CLASSIFIER() AS pattern_var,
        MATCH_NUMBER() AS match_num,
        A.price AS a_price,
        A.order_date AS a_date
    ALL ROWS PER MATCH
    PATTERN (A+ B+ C+)
    DEFINE
        A AS A.price > PREV(A.price) OR PREV(A.price) IS NULL,
        B AS B.price < PREV(B.price),
        C AS C.price > PREV(C.price)
);

SELECT *
FROM orders
MATCH_RECOGNIZE (
    PARTITION BY customer_id
    ORDER BY order_date
    MEASURES
        CLASSIFIER() AS pattern_var,
        MATCH_NUMBER() AS match_num,
        A.price AS price_value,
        A.order_date AS order_value
    ALL ROWS PER MATCH
    PATTERN (A?)
    DEFINE
        A AS A.price >= 200
);
