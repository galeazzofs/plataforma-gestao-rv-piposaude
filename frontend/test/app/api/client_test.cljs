(ns app.api.client-test
  (:require [cljs.test :refer-macros [deftest is testing]]
            [app.api.client :as client]))

(deftest error-body-test
  (testing "caminho ajax (JSON): body parseado vem aninhado em :response"
    (is (= {:error {:message "x"}}
           (client/error-body {:status 422 :failure :error
                               :response {:error {:message "x"}}}))))
  (testing "caminho multipart (fetch): body vem direto"
    (is (= {:error {:message "x"}}
           (client/error-body {:error {:message "x"}}))))
  (testing ":response nil cai para o mapa externo"
    (is (= {:status 0 :response nil}
           (client/error-body {:status 0 :response nil})))))

(deftest error-message-test
  (testing "extrai a mensagem nos dois shapes"
    (is (= "boom" (client/error-message
                   {:status 422 :response {:error {:message "boom"}}} "fb")))
    (is (= "boom" (client/error-message {:error {:message "boom"}} "fb"))))
  (testing "fallback quando não há envelope de erro"
    (is (= "fb" (client/error-message {:status 0} "fb")))
    (is (= "fb" (client/error-message nil "fb")))))
