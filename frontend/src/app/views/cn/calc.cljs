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

(defn regua-rampagem
  "Régua da rampagem: limites superiores INCLUSIVOS (≠ regua normal).
   Espelha _regua_rampagem do backend."
  [score]
  (cond
    (<= score 0.20) 0
    (<= score 0.40) 0.20
    (<= score 1.00) score
    (<= score 1.10) 1.20
    (<  score 1.40) 1.80
    :else 2.10))

(defn- round4 [x]
  (/ (js/Math.round (* x 10000)) 10000))

(defn- capped [num den]
  (if (and den (pos? den)) (min (/ num den) 1) 0))

(defn- uncapped [num den]
  (if (and den (pos? den)) (/ num den) 0))

(defn rampagem-sem-sao
  "Rampagem sem meta de SAO: negócios + emails, ambos com teto; bônus por SAO fora da meta."
  [{:keys [nivel neg_meta neg_real emails_meta emails_real sao_fora_da_meta bonus_sao]}]
  (let [atg   (round4 (+ (* 0.5 (capped (or (->num neg_real) 0) (or (->num neg_meta) 0)))
                         (* 0.5 (capped (or (->num emails_real) 0) (or (->num emails_meta) 0)))))
        gat   (regua-rampagem atg)
        base  (get cn-bases nivel 0)
        bonus (* (or (->num bonus_sao) 300) (or (->num sao_fora_da_meta) 0))]
    {:calc_mode "RAMPAGEM_SEM_SAO" :atingimento atg :gatilho gat
     :bonus_sao_amount bonus :commission_amount (+ (* base gat) bonus)
     :score_final atg :multiplicador gat :base base}))

(defn rampagem-com-sao
  "Rampagem com meta de SAO: SAO sem teto + qualis com teto; sem bônus."
  [{:keys [nivel sao_meta sao_real qualis_meta qualis_real]}]
  (let [atg  (round4 (+ (* 0.5 (uncapped (or (->num sao_real) 0) (or (->num sao_meta) 0)))
                        (* 0.5 (capped (or (->num qualis_real) 0) (or (->num qualis_meta) 0)))))
        gat  (regua-rampagem atg)
        base (get cn-bases nivel 0)]
    {:calc_mode "RAMPAGEM_COM_SAO" :atingimento atg :gatilho gat
     :bonus_sao_amount 0 :commission_amount (* base gat)
     :score_final atg :multiplicador gat :base base}))

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

(defn calculate-auto
  "Escolhe NORMAL / RAMPAGEM_SEM_SAO / RAMPAGEM_COM_SAO a partir de em_rampagem + sao_meta.
   Espelha simulate_cn_auto do backend."
  [{:keys [em_rampagem sao_meta] :as form}]
  (cond
    (not em_rampagem) (assoc (calculate form) :calc_mode "NORMAL")
    (pos? (or (->num sao_meta) 0)) (rampagem-com-sao form)
    :else (rampagem-sem-sao form)))
