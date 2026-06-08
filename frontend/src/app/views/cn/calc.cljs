(ns app.views.cn.calc
  "Pure CN commission math — mirrors backend/app/modules/commissions/simulator.py.
   Single source of truth on the frontend so the CN simulator and the RevOps
   monthly apuração never drift on the porte factor or the régua de pagamento."
  (:require [clojure.string :as str]))

(def cn-bases {"CN1" 2000 "CN2" 2500 "CN3" 3000})
(def porte-factors {"M" 375 "G+" 2000})

(defn ->num
  "Parse a number from a string/number, accepting pt-BR decimal commas.
   Returns nil when blank or unparseable."
  [v]
  (cond
    (number? v) v
    (and (string? v) (seq (str/trim v)))
    (let [n (js/parseFloat (str/replace (str/trim v) "," "."))]
      (when-not (js/isNaN n) n))
    :else nil))

(defn regua
  "Régua de pagamento: score → multiplicador."
  [score]
  (cond
    (< score 0.20) 0
    (< score 0.40) 0.20
    (< score 1.00) score
    (< score 1.10) 1.20
    (< score 1.40) 1.80
    :else 2.10))

(defn vidas-meta-from-sao
  "Monthly lives target derived from the SAO target and the CN porte factor."
  [sao-meta porte]
  (let [factor (get porte-factors porte)]
    (when (and factor (pos? (or sao-meta 0)))
      (* sao-meta factor))))

(defn calculate
  "Full CN commission breakdown for a form map. Mirrors simulate_cn()."
  [{:keys [nivel sao_meta sao_realizado vidas_meta vidas_realizado]}]
  (let [sao-meta (or (->num sao_meta) 0)
        sao-realizado (or (->num sao_realizado) 0)
        vidas-meta (or (->num vidas_meta) 0)
        vidas-realizado (or (->num vidas_realizado) 0)
        pct-sao (if (pos? sao-meta) (/ sao-realizado sao-meta) 0)
        pct-vidas (if (pos? vidas-meta)
                    (min (/ vidas-realizado vidas-meta) 1.5)
                    0)
        score (+ (* pct-sao 0.70) (* pct-vidas 0.30))
        multiplicador (regua score)
        base (get cn-bases nivel 0)]
    {:pct_sao pct-sao
     :pct_vidas pct-vidas
     :score_final score
     :multiplicador multiplicador
     :commission_amount (* base multiplicador)
     :base base}))
